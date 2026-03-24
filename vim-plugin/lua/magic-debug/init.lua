--[[
Magic Debug - Vim/Neovim Plugin

AI 驱动的调试器 Vim 插件。

Usage:
    require('magic-debug').setup({
        socket = "/tmp/magic-debug.sock",
        auto_start = true,
    })

Commands:
    :MagicDebugStart <program>  - 启动调试
    :MagicDebugStop             - 停止调试
    :MagicDebugContinue         - 继续执行
    :MagicDebugStepOver         - 单步跳过
    :MagicDebugStepInto         - 单步进入
    :MagicDebugStepOut          - 单步跳出
    :MagicDebugToggleBreakpoint - 切换断点
    :MagicDebugRefresh          - 刷新状态
]]

local M = {}

-- 默认配置
local default_config = {
    socket = "/tmp/magic-debug.sock",
    http_port = 8765,
    auto_start_server = true,
    server_command = "magic-debug",
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

-- 状态
local state = {
    connected = false,
    socket = nil,
    config = {},
    debug_state = {},
    augroup = nil,
}

--- 发送 RPC 请求
---@param method string 方法名
---@param params table|nil 参数
---@return table|nil 响应
local function rpc_call(method, params)
    if not state.connected or not state.socket then
        vim.notify("Magic Debug: Not connected", vim.log.levels.ERROR)
        return nil
    end
    
    local request = vim.json.encode({
        id = vim.loop.hrtime(),
        method = method,
        params = params or {},
    }) .. "\n"
    
    local ok, err = pcall(function()
        vim.fn.chansend(state.socket, request)
    end)
    
    if not ok then
        vim.notify("Magic Debug: Failed to send request: " .. err, vim.log.levels.ERROR)
        state.connected = false
        return nil
    end
    
    -- 读取响应
    local response = vim.fn.chanread(state.socket, 5000)
    if response then
        local decoded = vim.json.decode(response)
        return decoded
    end
    
    return nil
end

--- 连接到 RPC 服务器
---@return boolean 是否成功
local function connect()
    if state.connected then
        return true
    end
    
    -- 检查 socket 文件是否存在
    local socket_path = state.config.socket
    if vim.fn.filereadable(socket_path) == 0 then
        if state.config.auto_start_server then
            -- 尝试启动服务器
            vim.notify("Magic Debug: Starting server...", vim.log.levels.INFO)
            vim.fn.system(state.config.server_command .. " &")
            vim.wait(1000) -- 等待服务器启动
        end
        
        if vim.fn.filereadable(socket_path) == 0 then
            vim.notify("Magic Debug: Socket not found: " .. socket_path, vim.log.levels.ERROR)
            return false
        end
    end
    
    -- 连接
    local ok, sock = pcall(function()
        return vim.fn.sockconnect("unix", socket_path, { rpc = false })
    end)
    
    if not ok or sock == 0 then
        vim.notify("Magic Debug: Failed to connect to socket", vim.log.levels.ERROR)
        return false
    end
    
    state.socket = sock
    state.connected = true
    
    -- 测试连接
    local response = rpc_call("ping")
    if not response or not response.result or not response.result.pong then
        state.connected = false
        state.socket = nil
        vim.notify("Magic Debug: Server not responding", vim.log.levels.ERROR)
        return false
    end
    
    vim.notify("Magic Debug: Connected", vim.log.levels.INFO)
    return true
end

--- 断开连接
local function disconnect()
    if state.socket then
        vim.fn.chanclose(state.socket)
        state.socket = nil
    end
    state.connected = false
end

--- 更新调试状态
local function update_state()
    local response = rpc_call("getState")
    if response and response.result then
        state.debug_state = response.result.state or {}
        
        -- 更新 UI
        M.update_signs()
        
        -- 触发事件
        vim.api.nvim_exec_autocmds("User", {
            pattern = "MagicDebugStateChanged",
            data = state.debug_state,
        })
    end
end

--- 设置断点标记
local function set_breakpoint_signs()
    -- 清除旧标记
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

--- 设置当前行标记
local function set_current_line_sign()
    -- 清除旧标记
    vim.fn.sign_unplace("MagicDebugCurrent")
    
    local current_file = state.debug_state.currentLocation and state.debug_state.currentLocation.path
    local current_line = state.debug_state.currentLocation and state.debug_state.currentLocation.line
    
    if current_file and current_line then
        vim.fn.sign_place(0, "MagicDebugCurrent", "MagicDebugCurrentLine", current_file, {
            lnum = current_line,
        })
        
        -- 打开文件并跳转到当前行
        vim.cmd("edit " .. vim.fn.fnameescape(current_file))
        vim.cmd("normal! " .. current_line .. "Gzz")
    end
end

--- 更新所有标记
function M.update_signs()
    set_breakpoint_signs()
    set_current_line_sign()
end

--- 设置断点
---@param file string|nil 文件路径
---@param line number|nil 行号
function M.set_breakpoint(file, line)
    if not connect() then return end
    
    file = file or vim.fn.expand("%:p")
    line = line or vim.fn.line(".")
    
    local response = rpc_call("setBreakpoint", {
        file = file,
        line = line,
    })
    
    if response and response.result and response.result.success then
        vim.notify(string.format("Breakpoint set at %s:%d", file, line), vim.log.levels.INFO)
        update_state()
    else
        vim.notify("Failed to set breakpoint", vim.log.levels.ERROR)
    end
end

--- 移除断点
---@param file string|nil 文件路径
---@param line number|nil 行号
function M.remove_breakpoint(file, line)
    if not connect() then return end
    
    file = file or vim.fn.expand("%:p")
    line = line or vim.fn.line(".")
    
    local response = rpc_call("removeBreakpoint", {
        file = file,
        line = line,
    })
    
    if response and response.result and response.result.success then
        vim.notify(string.format("Breakpoint removed at %s:%d", file, line), vim.log.levels.INFO)
        update_state()
    end
end

--- 切换断点
---@param file string|nil 文件路径
---@param line number|nil 行号
function M.toggle_breakpoint(file, line)
    if not connect() then return end
    
    file = file or vim.fn.expand("%:p")
    line = line or vim.fn.line(".")
    
    local response = rpc_call("toggleBreakpoint", {
        file = file,
        line = line,
    })
    
    if response and response.result then
        update_state()
    end
end

--- 清除所有断点
function M.clear_breakpoints()
    if not connect() then return end
    
    local response = rpc_call("clearBreakpoints")
    
    if response and response.result and response.result.success then
        vim.notify("All breakpoints cleared", vim.log.levels.INFO)
        update_state()
    end
end

--- 启动调试
---@param program string 程序路径
---@param opts table|nil 选项
function M.start(program, opts)
    if not connect() then return end
    
    opts = opts or {}
    
    local response = rpc_call("start", {
        program = program,
        args = opts.args or {},
        cwd = opts.cwd or vim.fn.getcwd(),
        env = opts.env or {},
        stopOnEntry = opts.stop_on_entry or false,
    })
    
    if response and response.result and response.result.success then
        vim.notify("Debugging started: " .. program, vim.log.levels.INFO)
        update_state()
    else
        local error = response and response.result and response.result.error or "Unknown error"
        vim.notify("Failed to start debugging: " .. error, vim.log.levels.ERROR)
    end
end

--- 停止调试
function M.stop()
    if not connect() then return end
    
    local response = rpc_call("stop")
    
    if response and response.result and response.result.success then
        vim.notify("Debugging stopped", vim.log.levels.INFO)
        state.debug_state = {}
        M.update_signs()
    end
end

--- 继续执行
function M.continue()
    if not connect() then return end
    
    local response = rpc_call("continue")
    
    if response and response.result and response.result.success then
        update_state()
    end
end

--- 暂停执行
function M.pause()
    if not connect() then return end
    
    rpc_call("pause")
end

--- 单步跳过
function M.step_over()
    if not connect() then return end
    
    local response = rpc_call("stepOver")
    
    if response and response.result and response.result.success then
        update_state()
    end
end

--- 单步进入
function M.step_into()
    if not connect() then return end
    
    local response = rpc_call("stepInto")
    
    if response and response.result and response.result.success then
        update_state()
    end
end

--- 单步跳出
function M.step_out()
    if not connect() then return end
    
    local response = rpc_call("stepOut")
    
    if response and response.result and response.result.success then
        update_state()
    end
end

--- 刷新状态
function M.refresh()
    if not connect() then return end
    
    local response = rpc_call("refresh")
    
    if response and response.result and response.result.success then
        update_state()
    end
end

--- 求值表达式
---@param expression string 表达式
---@return table|nil 结果
function M.evaluate(expression)
    if not connect() then return nil end
    
    local response = rpc_call("evaluate", {
        expression = expression,
        context = "repl",
    })
    
    if response and response.result then
        return response.result
    end
    
    return nil
end

--- 获取变量
---@param variables_reference number 变量引用
---@return table|nil 变量列表
function M.get_variables(variables_reference)
    if not connect() then return nil end
    
    local response = rpc_call("getVariables", {
        variablesReference = variables_reference,
    })
    
    if response and response.result then
        return response.result.variables
    end
    
    return nil
end

--- 获取调试状态
---@return table 状态
function M.get_state()
    return state.debug_state
end

--- 是否正在调试
---@return boolean
function M.is_debugging()
    local status = state.debug_state.status
    return status ~= nil and status ~= "idle" and status ~= "terminated"
end

--- 打开调试 UI
function M.open_ui()
    -- 创建浮动窗口显示调试信息
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
    
    -- 更新内容
    local function update_content()
        local lines = { "=== Magic Debug ===", "" }
        
        -- 状态
        local s = state.debug_state
        table.insert(lines, "Status: " .. (s.status or "idle"))
        table.insert(lines, "Program: " .. (s.program or "none"))
        table.insert(lines, "")
        
        -- 当前位置
        if s.currentLocation then
            table.insert(lines, string.format("Current: %s:%d",
                s.currentLocation.path or "?",
                s.currentLocation.line or 0))
            table.insert(lines, "")
        end
        
        -- 调用栈
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
        
        -- 断点
        local bp_count = 0
        for _, bps in pairs(s.breakpoints or {}) do
            bp_count = bp_count + #bps
        end
        table.insert(lines, string.format("Breakpoints: %d", bp_count))
        
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    end
    
    update_content()
    
    -- 自动更新
    vim.api.nvim_create_autocmd("User", {
        pattern = "MagicDebugStateChanged",
        callback = update_content,
    })
    
    -- 关闭窗口
    vim.keymap.set("n", "q", function()
        vim.api.nvim_win_close(win, true)
    end, { buffer = buf })
end

--- 设置插件
---@param config table|nil 配置
function M.setup(config)
    state.config = vim.tbl_deep_extend("force", default_config, config or {})
    
    -- 定义标记
    vim.fn.sign_define("MagicDebugBreakpoint", {
        text = state.config.signs.breakpoint,
        texthl = state.config.highlights.breakpoint,
    })
    
    vim.fn.sign_define("MagicDebugCurrentLine", {
        text = state.config.signs.current_line,
        texthl = state.config.highlights.current_line,
    })
    
    -- 创建命令
    vim.api.nvim_create_user_command("MagicDebugStart", function(args)
        M.start(args.args)
    end, { nargs = 1 })
    
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
    
    -- 创建自动命令组
    state.augroup = vim.api.nvim_create_augroup("MagicDebug", { clear = true })
    
    -- 退出时断开连接
    vim.api.nvim_create_autocmd("VimLeavePre", {
        group = state.augroup,
        callback = disconnect,
    })
    
    vim.notify("Magic Debug initialized", vim.log.levels.INFO)
end

return M
