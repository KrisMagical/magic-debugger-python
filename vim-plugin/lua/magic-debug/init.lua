local M = {}

local default_config = {
    socket = "/tmp/magic-debug.sock",
    rpc_transport = "auto",
    rpc_host = "127.0.0.1",
    rpc_port = 8766,
    rpc_socket_path = nil,
    http_port = 8765,
    auto_start_server = true,
    server_command = { "magic-debug", "--rpc" },
    request_timeout = 5000,
    signs = {
        breakpoint = "B",
        breakpoint_cond = "C",
        current_line = ">",
    },
    highlights = {
        breakpoint = "ErrorMsg",
        current_line = "Search",
    },
}

local state = {
    connected = false,
    socket = nil,
    config = {},
    debug_state = {},
    augroup = nil,
    next_request_id = 1,
    pending_requests = {},
    rpc_buffer = "",
    logs = {},
    server_job = nil,
    last_launch_config = nil,
    rpc_endpoint = nil,
}

local function log(level, message, details)
    local entry = {
        time = os.date("%H:%M:%S"),
        level = level,
        message = message,
        details = details,
    }
    table.insert(state.logs, entry)
    if #state.logs > 500 then
        table.remove(state.logs, 1)
    end
    if level == "error" then
        vim.notify("Magic Debug: " .. message, vim.log.levels.ERROR)
    elseif level == "warn" then
        vim.notify("Magic Debug: " .. message, vim.log.levels.WARN)
    end
end

local function notify_rpc_error(response, fallback)
    local err = response and response.error
    local message = fallback or "RPC request failed"
    if err and err.message then
        message = err.message
    end
    log("error", message, err)
end

local function response_ok(response)
    return response and response.type == "response" and response.success == true
end

local function make_request(method, params)
    local id = state.next_request_id
    state.next_request_id = state.next_request_id + 1
    return {
        id = id,
        method = method,
        params = params or {},
    }
end

local function handle_rpc_event(event, body)
    log("debug", "RPC event: " .. tostring(event), body)
    if event == "state_changed" and type(body) == "table" then
        state.debug_state = body
    end
    vim.schedule(function()
        M.update_signs()
        vim.api.nvim_exec_autocmds("User", {
            pattern = "MagicDebugStateChanged",
            data = body,
        })
    end)
end

local function handle_rpc_response(msg)
    local pending = state.pending_requests[msg.id]
    if not pending then
        log("warn", "Received response for unknown request id: " .. tostring(msg.id), msg)
        return
    end
    state.pending_requests[msg.id] = nil
    pending.response = msg
    if pending.callback then
        pending.callback(msg)
    end
end

local function dispatch_rpc_message(msg)
    if type(msg) ~= "table" then
        log("warn", "Ignoring non-table RPC message", msg)
        return
    end

    if msg.type == "response" then
        handle_rpc_response(msg)
    elseif msg.type == "event" then
        handle_rpc_event(msg.event, msg.body)
    else
        log("warn", "Ignoring unknown RPC message type: " .. tostring(msg.type), msg)
    end
end

local function append_rpc_data(data)
    if type(data) == "table" then
        return table.concat(data, "\n")
    end
    return tostring(data or "")
end

local function on_rpc_data(data)
    state.rpc_buffer = state.rpc_buffer .. append_rpc_data(data)

    while true do
        local newline = state.rpc_buffer:find("\n", 1, true)
        if not newline then
            break
        end

        local line = state.rpc_buffer:sub(1, newline - 1)
        state.rpc_buffer = state.rpc_buffer:sub(newline + 1)

        if vim.trim(line) ~= "" then
            local ok, msg = pcall(vim.json.decode, line)
            if ok then
                dispatch_rpc_message(msg)
            else
                log("warn", "Invalid RPC JSON message", line)
            end
        end
    end
end

local function rpc_call(method, params, callback)
    if not state.connected or not state.socket then
        log("error", "Not connected")
        return nil
    end

    local request = make_request(method, params)
    local done = false
    local response = nil

    state.pending_requests[request.id] = {
        method = method,
        timestamp = (vim.uv or vim.loop).hrtime(),
        callback = function(msg)
            response = msg
            done = true
            if callback then
                callback(msg)
            end
        end,
    }

    local ok, err = pcall(function()
        vim.fn.chansend(state.socket, vim.json.encode(request) .. "\n")
    end)

    if not ok then
        state.pending_requests[request.id] = nil
        state.connected = false
        log("error", "Failed to send RPC request", err)
        return nil
    end

    vim.wait(state.config.request_timeout or 5000, function()
        return done
    end, 20)

    if not done then
        state.pending_requests[request.id] = nil
        response = {
            type = "response",
            id = request.id,
            success = false,
            error = {
                code = "TIMEOUT",
                message = "RPC request timed out: " .. method,
                details = {},
            },
        }
        if callback then
            callback(response)
        end
    end

    return response
end

local function normalize_server_command(command)
    if type(command) == "table" then
        return vim.deepcopy(command)
    end
    if type(command) == "string" then
        log("warn", "String server_command is deprecated; use an array instead")
        return { command }
    end
    return nil
end

local function is_windows()
    return vim.loop.os_uname().sysname:lower():match("windows") ~= nil
        or vim.fn.has("win32") == 1
end

local function default_socket_path()
    return state.config.rpc_socket_path or state.config.socket or "/tmp/magic-debug.sock"
end

local function resolve_rpc_transport()
    local requested = state.config.rpc_transport or "auto"
    if requested == "auto" then
        return is_windows() and "tcp" or "unix"
    end
    return requested
end

local function current_rpc_endpoint(transport)
    transport = transport or resolve_rpc_transport()
    if transport == "tcp" then
        return {
            transport = "tcp",
            host = state.config.rpc_host or "127.0.0.1",
            port = state.config.rpc_port or 8766,
            label = string.format("tcp://%s:%s", state.config.rpc_host or "127.0.0.1", state.config.rpc_port or 8766),
        }
    end
    return {
        transport = "unix",
        socket_path = default_socket_path(),
        label = "unix:" .. default_socket_path(),
    }
end

local function append_rpc_transport_args(command)
    local endpoint = current_rpc_endpoint()
    table.insert(command, "--rpc-transport")
    table.insert(command, state.config.rpc_transport or "auto")
    if endpoint.transport == "tcp" then
        table.insert(command, "--rpc-host")
        table.insert(command, endpoint.host)
        table.insert(command, "--rpc-port")
        table.insert(command, tostring(endpoint.port))
    else
        table.insert(command, "--rpc-socket")
        table.insert(command, endpoint.socket_path)
    end
    return command
end

local function start_server()
    if state.server_job then
        return true
    end

    local command = normalize_server_command(state.config.server_command)
    if not command or #command == 0 then
        log("error", "Invalid server_command")
        return false
    end
    command = append_rpc_transport_args(command)

    log("info", "Starting Magic Debug server", command)

    if vim.system then
        state.server_job = vim.system(command, {
            text = true,
            stdout = function(_, data)
                if data and data ~= "" then
                    log("info", "server stdout", data)
                end
            end,
            stderr = function(_, data)
                if data and data ~= "" then
                    log("warn", "server stderr", data)
                end
            end,
        }, function(result)
            log(result.code == 0 and "info" or "warn", "server exited", result)
            state.server_job = nil
        end)
        return true
    end

    local job = vim.fn.jobstart(command, {
        stdout_buffered = false,
        stderr_buffered = false,
        on_stdout = function(_, data)
            if data then
                log("info", "server stdout", data)
            end
        end,
        on_stderr = function(_, data)
            if data then
                log("warn", "server stderr", data)
            end
        end,
        on_exit = function(_, code)
            log(code == 0 and "info" or "warn", "server exited", { code = code })
            state.server_job = nil
        end,
    })

    if job <= 0 then
        log("error", "Failed to start Magic Debug server")
        return false
    end

    state.server_job = job
    return true
end

local function stop_server()
    if not state.server_job then
        return
    end
    if type(state.server_job) == "number" then
        vim.fn.jobstop(state.server_job)
    elseif state.server_job.kill then
        state.server_job:kill(15)
    end
    state.server_job = nil
end

local function connect_endpoint(endpoint)
    if endpoint.transport == "unix" then
        if vim.fn.filereadable(endpoint.socket_path) == 0 then
            return false, "Socket not found: " .. endpoint.socket_path
        end
        return pcall(function()
            return vim.fn.sockconnect("unix", endpoint.socket_path, {
                rpc = false,
                on_data = function(_, data)
                    on_rpc_data(data)
                end,
            })
        end)
    end

    return pcall(function()
        return vim.fn.sockconnect("tcp", endpoint.host .. ":" .. tostring(endpoint.port), {
            rpc = false,
            on_data = function(_, data)
                on_rpc_data(data)
            end,
        })
    end)
end

local function connect()
    if state.connected then
        return true
    end

    if state.config.auto_start_server then
        if not start_server() then
            return false
        end
        vim.wait(1000)
    end

    local endpoint = current_rpc_endpoint()
    local ok, sock = connect_endpoint(endpoint)

    if not ok or sock == 0 then
        if state.config.rpc_transport == "auto" and endpoint.transport == "unix" then
            log("warn", "Unix RPC connection failed; trying TCP fallback", endpoint)
            endpoint = current_rpc_endpoint("tcp")
            ok, sock = connect_endpoint(endpoint)
        end

        if not ok or sock == 0 then
            log("error", "Failed to connect to RPC endpoint: " .. endpoint.label)
            return false
        end
    end

    state.socket = sock
    state.connected = true
    state.rpc_buffer = ""
    state.rpc_endpoint = endpoint

    local response = rpc_call("ping")
    if not response_ok(response) or not response.result or not response.result.pong then
        state.connected = false
        state.socket = nil
        notify_rpc_error(response, "Server not responding")
        return false
    end

    vim.notify("Magic Debug: Connected to " .. endpoint.label, vim.log.levels.INFO)
    return true
end

local function disconnect()
    if state.socket then
        vim.fn.chanclose(state.socket)
        state.socket = nil
    end
    state.connected = false
    state.pending_requests = {}
    state.rpc_buffer = ""
end

local function update_state()
    local response = rpc_call("getState")
    if response_ok(response) and response.result then
        state.debug_state = response.result.state or {}
        M.update_signs()
        vim.api.nvim_exec_autocmds("User", {
            pattern = "MagicDebugStateChanged",
            data = state.debug_state,
        })
    elseif response then
        notify_rpc_error(response, "Failed to refresh state")
    end
end

local function set_breakpoint_signs()
    vim.fn.sign_unplace("MagicDebugBreakpoint")

    local breakpoints = state.debug_state.breakpoints or {}
    for file, bps in pairs(breakpoints) do
        for _, bp in ipairs(bps) do
            if bp.verified then
                vim.fn.sign_place(0, "MagicDebugBreakpoint", "MagicDebugBreakpoint", file, {
                    lnum = bp.line,
                })
            end
        end
    end
end

local function set_current_line_sign()
    vim.fn.sign_unplace("MagicDebugCurrent")

    local current_file = state.debug_state.currentLocation and state.debug_state.currentLocation.path
    local current_line = state.debug_state.currentLocation and state.debug_state.currentLocation.line

    if current_file and current_line then
        vim.fn.sign_place(0, "MagicDebugCurrent", "MagicDebugCurrentLine", current_file, {
            lnum = current_line,
        })
        vim.cmd("edit " .. vim.fn.fnameescape(current_file))
        vim.cmd("normal! " .. current_line .. "Gzz")
    end
end

function M.update_signs()
    set_breakpoint_signs()
    set_current_line_sign()
end

local function find_launch_config()
    local names = { "magic-debug.json", ".magic-debug.json" }
    local roots = { vim.fn.getcwd() }
    local buffer_dir = vim.fn.expand("%:p:h")
    if buffer_dir ~= "" then
        table.insert(roots, buffer_dir)
    end

    if vim.fs and vim.fs.find then
        for _, root in ipairs(roots) do
            local found = vim.fs.find(names, { path = root, upward = true, limit = 1 })
            if #found > 0 then
                return found[1]
            end
        end
    end

    for _, root in ipairs(roots) do
        local dir = root
        while dir and dir ~= "" do
            for _, name in ipairs(names) do
                local candidate = dir .. "/" .. name
                if vim.fn.filereadable(candidate) == 1 then
                    return candidate
                end
            end
            local parent = vim.fn.fnamemodify(dir, ":h")
            if parent == dir then
                break
            end
            dir = parent
        end
    end
    return nil
end

local function load_launch_config()
    local path = find_launch_config()
    if not path then
        log("error", "No magic-debug.json or .magic-debug.json found")
        return nil
    end

    local ok, lines = pcall(vim.fn.readfile, path)
    if not ok then
        log("error", "Failed to read config: " .. path)
        return nil
    end

    local ok_decode, config = pcall(vim.json.decode, table.concat(lines, "\n"))
    if not ok_decode then
        log("error", "Invalid JSON config: " .. path, config)
        return nil
    end

    config.cwd = config.cwd or vim.fn.fnamemodify(path, ":h")
    return config
end

local function build_launch_config(program, opts)
    opts = opts or {}
    if program and program ~= "" then
        return {
            program = program,
            args = opts.args or {},
            cwd = opts.cwd or vim.fn.getcwd(),
            env = opts.env or {},
            stopAtEntry = opts.stopAtEntry or opts.stop_on_entry or false,
            gdbPath = opts.gdbPath,
        }
    end
    return load_launch_config()
end

function M.set_breakpoint(file, line)
    if not connect() then return end

    file = file or vim.fn.expand("%:p")
    line = line or vim.fn.line(".")

    local response = rpc_call("setBreakpoint", {
        file = file,
        line = line,
    })

    if response_ok(response) then
        vim.notify(string.format("Breakpoint set at %s:%d", file, line), vim.log.levels.INFO)
        update_state()
    else
        notify_rpc_error(response, "Failed to set breakpoint")
    end
end

function M.remove_breakpoint(file, line)
    if not connect() then return end

    file = file or vim.fn.expand("%:p")
    line = line or vim.fn.line(".")

    local response = rpc_call("removeBreakpoint", {
        file = file,
        line = line,
    })

    if response_ok(response) then
        vim.notify(string.format("Breakpoint removed at %s:%d", file, line), vim.log.levels.INFO)
        update_state()
    else
        notify_rpc_error(response, "Failed to remove breakpoint")
    end
end

function M.toggle_breakpoint(file, line)
    if not connect() then return end

    file = file or vim.fn.expand("%:p")
    line = line or vim.fn.line(".")

    local response = rpc_call("toggleBreakpoint", {
        file = file,
        line = line,
    })

    if response_ok(response) then
        update_state()
    else
        notify_rpc_error(response, "Failed to toggle breakpoint")
    end
end

function M.clear_breakpoints()
    if not connect() then return end

    local response = rpc_call("clearBreakpoints")
    if response_ok(response) then
        vim.notify("All breakpoints cleared", vim.log.levels.INFO)
        update_state()
    else
        notify_rpc_error(response, "Failed to clear breakpoints")
    end
end

function M.start(program, opts)
    if not connect() then return end

    local config = build_launch_config(program, opts)
    if not config or not config.program or config.program == "" then
        log("error", "Missing program in launch config")
        return
    end

    local params = {
        program = config.program,
        args = config.args or {},
        cwd = config.cwd or vim.fn.getcwd(),
        env = config.env or {},
        stopAtEntry = config.stopAtEntry or false,
        gdbPath = config.gdbPath,
    }
    state.last_launch_config = params

    local response = rpc_call("start", params)
    if response_ok(response) then
        vim.notify("Debugging started: " .. params.program, vim.log.levels.INFO)
        update_state()
    else
        notify_rpc_error(response, "Failed to start debugging")
    end
end

function M.stop()
    if not connect() then return end

    local response = rpc_call("stop")
    if response_ok(response) then
        vim.notify("Debugging stopped", vim.log.levels.INFO)
        state.debug_state = {}
        M.update_signs()
    else
        notify_rpc_error(response, "Failed to stop debugging")
    end
end

function M.continue()
    if not connect() then return end

    local response = rpc_call("continue")
    if response_ok(response) then
        update_state()
    else
        notify_rpc_error(response, "Failed to continue")
    end
end

function M.pause()
    if not connect() then return end
    local response = rpc_call("pause")
    if not response_ok(response) then
        notify_rpc_error(response, "Failed to pause")
    end
end

function M.step_over()
    if not connect() then return end

    local response = rpc_call("stepOver")
    if response_ok(response) then
        update_state()
    else
        notify_rpc_error(response, "Failed to step over")
    end
end

function M.step_into()
    if not connect() then return end

    local response = rpc_call("stepInto")
    if response_ok(response) then
        update_state()
    else
        notify_rpc_error(response, "Failed to step into")
    end
end

function M.step_out()
    if not connect() then return end

    local response = rpc_call("stepOut")
    if response_ok(response) then
        update_state()
    else
        notify_rpc_error(response, "Failed to step out")
    end
end

function M.refresh()
    if not connect() then return end

    local response = rpc_call("refresh")
    if response_ok(response) then
        update_state()
    else
        notify_rpc_error(response, "Failed to refresh")
    end
end

function M.evaluate(expression)
    if not connect() then return nil end

    local response = rpc_call("evaluate", {
        expression = expression,
        context = "repl",
    })

    if response_ok(response) then
        return response.result
    end
    notify_rpc_error(response, "Failed to evaluate expression")
    return nil
end

function M.get_variables(variables_reference)
    if not connect() then return nil end

    local response = rpc_call("getVariables", {
        variablesReference = variables_reference,
    })

    if response_ok(response) then
        return response.result.variables
    end
    notify_rpc_error(response, "Failed to get variables")
    return nil
end

function M.get_state()
    return state.debug_state
end

function M.is_debugging()
    local status = state.debug_state.status
    return status ~= nil and status ~= "idle" and status ~= "terminated"
end

function M.open_logs()
    local lines = {}
    for _, entry in ipairs(state.logs) do
        local detail = ""
        if entry.details ~= nil then
            detail = " " .. vim.inspect(entry.details)
        end
        table.insert(lines, string.format("[%s] %s %s%s", entry.time, entry.level, entry.message, detail))
    end
    if #lines == 0 then
        lines = { "Magic Debug logs are empty." }
    end

    local buf = vim.api.nvim_create_buf(false, true)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
end

function M.reconnect()
    disconnect()
    if connect() then
        vim.notify("Magic Debug: Reconnected", vim.log.levels.INFO)
    end
end

function M.open_ui()
    local buf = vim.api.nvim_create_buf(false, true)
    local width = math.floor(vim.o.columns * 0.6)
    local height = math.floor(vim.o.lines * 0.6)
    local row = math.floor((vim.o.lines - height) / 2)
    local col = math.floor((vim.o.columns - width) / 2)

    local opts = {
        relative = "editor",
        width = width,
        height = height,
        row = row,
        col = col,
        style = "minimal",
        border = "rounded",
        title = " Magic Debug ",
        title_pos = "center",
    }

    local win = vim.api.nvim_open_win(buf, true, opts)

    local function update_content()
        local lines = { "=== Magic Debug ===", "" }
        local s = state.debug_state
        table.insert(lines, "Status: " .. (s.status or "idle"))
        table.insert(lines, "Program: " .. (s.program or "none"))
        table.insert(lines, "")

        if s.currentLocation then
            table.insert(lines, string.format("Current: %s:%d",
                s.currentLocation.path or "?",
                s.currentLocation.line or 0))
            table.insert(lines, "")
        end

        if s.stackFrames and #s.stackFrames > 0 then
            table.insert(lines, "=== Stack Frames ===")
            for i, frame in ipairs(s.stackFrames) do
                if i > 10 then break end
                table.insert(lines, string.format("%d. %s (%s:%d)",
                    i,
                    frame.name or "?",
                    frame.source and frame.source.path or "?",
                    frame.line or 0))
            end
            table.insert(lines, "")
        end

        local bp_count = 0
        for _, bps in pairs(s.breakpoints or {}) do
            bp_count = bp_count + #bps
        end
        table.insert(lines, string.format("Breakpoints: %d", bp_count))

        vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    end

    update_content()

    vim.api.nvim_create_autocmd("User", {
        pattern = "MagicDebugStateChanged",
        callback = update_content,
    })

    vim.keymap.set("n", "q", function()
        vim.api.nvim_win_close(win, true)
    end, { buffer = buf })
end

function M.setup(config)
    state.config = vim.tbl_deep_extend("force", default_config, config or {})

    vim.fn.sign_define("MagicDebugBreakpoint", {
        text = state.config.signs.breakpoint,
        texthl = state.config.highlights.breakpoint,
    })

    vim.fn.sign_define("MagicDebugCurrentLine", {
        text = state.config.signs.current_line,
        texthl = state.config.highlights.current_line,
    })

    vim.api.nvim_create_user_command("MagicDebugStart", function(args)
        M.start(args.args)
    end, { nargs = "?" })

    vim.api.nvim_create_user_command("MagicDebugStop", function()
        M.stop()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugContinue", function()
        M.continue()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugStepOver", function()
        M.step_over()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugStepInto", function()
        M.step_into()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugStepOut", function()
        M.step_out()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugToggleBreakpoint", function()
        M.toggle_breakpoint()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugClearBreakpoints", function()
        M.clear_breakpoints()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugRefresh", function()
        M.refresh()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugUI", function()
        M.open_ui()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugLogs", function()
        M.open_logs()
    end, {})

    vim.api.nvim_create_user_command("MagicDebugReconnect", function()
        M.reconnect()
    end, {})

    state.augroup = vim.api.nvim_create_augroup("MagicDebug", { clear = true })

    vim.api.nvim_create_autocmd("VimLeavePre", {
        group = state.augroup,
        callback = function()
            disconnect()
            stop_server()
        end,
    })

    vim.notify("Magic Debug initialized", vim.log.levels.INFO)
end

M._test = {
    make_request = make_request,
    dispatch_rpc_message = dispatch_rpc_message,
    handle_rpc_response = handle_rpc_response,
    handle_rpc_event = handle_rpc_event,
    on_rpc_data = on_rpc_data,
    state = state,
}

return M
