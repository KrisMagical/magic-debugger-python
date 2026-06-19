# Magic Debug

Magic Debug is a GDB DAP based debugger backend and Vim/Neovim integration for
C/C++ debugging workflows.

Magic Debug is currently in beta. The official beta support matrix targets
Linux and macOS with Python 3.10-3.12 and GDB DAP. Windows is not part of the
official beta support matrix. The core GDB DAP backend, DAP framing, RPC
transport, diagnostics, packaging, and basic Neovim integration have been
stabilized, but users should still expect environment-specific GDB DAP
differences.

The backend talks to GDB through:

```bash
gdb --interpreter=dap
```

This project is currently focused on GDB DAP. It is not an LLDB backend, and
the current workflow requires GDB rather than an LLDB adapter.

## Overview

Magic Debug provides:

- Python backend process management for GDB DAP.
- A DAP client and DebugController.
- HTTP API for tools and automation.
- Line-delimited JSON RPC server for editor clients.
- Neovim Lua plugin with request id based RPC response/event dispatch.
- RPC transport selection: `auto`, `unix`, or `tcp`.
- `magic-debug doctor` and `magic-debug --check --json` diagnostics.

## Requirements

- Supported OS: Linux and macOS.
- Supported Python: 3.10, 3.11, and 3.12.
- GDB with `gdb --interpreter=dap` support for real debugging.
- GCC or Clang for the minimal C example and real e2e test.
- Neovim only if you use the Lua plugin.

Platform defaults:

- Linux/macOS: RPC `auto` uses Unix Domain Socket by default.
- TCP remains available for local debugging, forwarding, and troubleshooting.
- Windows is not officially supported in this beta.

Missing `gdb` does not break pure Python unit tests. `magic-debug doctor` reports
it as a warning because real debugging still needs GDB.

## Installation

Development install:

```bash
python -m pip install -e .
```

Build a wheel and source distribution:

```bash
python -m pip install build
python -m build
```

Install a built wheel:

```bash
python -m pip install dist/*.whl
```

Verify the CLI:

```bash
magic-debug --help
magic-debug doctor
magic-debug --check --json
```

When working from the source tree, `python main.py --help` is also supported.

## Quick Start

Shortest source-tree path:

```bash
python -m pip install -e .
magic-debug doctor
gcc -g -O0 tests/fixtures/test_sample.c -o /tmp/test_sample
magic-debug --rpc --rpc-transport auto
```

Then in Neovim:

```vim
:MagicDebugStart /tmp/test_sample
:MagicDebugToggleBreakpoint
:MagicDebugContinue
:MagicDebugLogs
```

Run diagnostics:

```bash
magic-debug doctor
```

Start the backend with automatic RPC transport:

```bash
magic-debug --rpc --rpc-transport auto
```

Explicit TCP example:

```bash
magic-debug --rpc --rpc-transport tcp --rpc-host 127.0.0.1 --rpc-port 8766
```

Explicit Unix socket example:

```bash
magic-debug --rpc --rpc-transport unix --rpc-socket /tmp/magic-debug.sock
```

HTTP uses port `8765` by default. RPC TCP uses port `8766` by default. Do not
confuse the HTTP port with the RPC port.

## Minimal C Debugging Example

The repository includes [tests/fixtures/test_sample.c](tests/fixtures/test_sample.c):

```c
int main(void) {
    int x = 1;
    x += 2;
    return x;
}
```

Compile on Linux/macOS:

```bash
gcc -g -O0 tests/fixtures/test_sample.c -o /tmp/test_sample
```

Run diagnostics:

```bash
magic-debug doctor
```

Start the backend:

```bash
magic-debug --rpc --rpc-transport auto
```

In Neovim:

```vim
:MagicDebugStart /tmp/test_sample
:MagicDebugToggleBreakpoint
:MagicDebugContinue
:MagicDebugLogs
:MagicDebugReconnect
```

Expected result:

- The backend starts successfully.
- A breakpoint can be toggled in the current source buffer.
- Continue runs the program until a breakpoint or `main`-adjacent stop.
- `stackTrace` contains a frame for `main`.
- Plugin/server logs are available with `:MagicDebugLogs`.

## Neovim Plugin Setup

Minimal runtimepath setup:

```lua
vim.opt.rtp:append("/path/to/magic-debugger-python-main/vim-plugin")
require("magic-debug").setup({
  rpc_transport = "auto",
  server_command = { "magic-debug", "--rpc", "--rpc-transport", "auto" },
})
```

Example with `lazy.nvim`:

```lua
return {
  {
    dir = "/path/to/magic-debug/vim-plugin",
    config = function()
      require("magic-debug").setup({
        rpc_transport = "auto",
        rpc_host = "127.0.0.1",
        rpc_port = 8766,
        rpc_socket_path = nil,
        auto_start_server = true,
        server_command = { "magic-debug", "--rpc" },
      })
    end,
  },
}
```

Useful commands:

```vim
:MagicDebugStart ./program
:MagicDebugStart
:MagicDebugToggleBreakpoint
:MagicDebugContinue
:MagicDebugStepOver
:MagicDebugStepInto
:MagicDebugStepOut
:MagicDebugStop
:MagicDebugUI
:MagicDebugLogs
:MagicDebugReconnect
```

`:MagicDebugStart` with no argument searches for `magic-debug.json` or
`.magic-debug.json`.

## Configuration File

The Neovim plugin searches for:

- `magic-debug.json`
- `.magic-debug.json`

Search starts from the current working directory and current buffer directory,
then walks upward toward the project root.

Example:

```json
{
  "program": "/tmp/test_sample",
  "args": [],
  "cwd": ".",
  "env": {
    "EXAMPLE": "1"
  },
  "stopAtEntry": false,
  "gdbPath": "gdb",
  "rpc_transport": "auto",
  "rpc_host": "127.0.0.1",
  "rpc_port": 8766,
  "rpc_socket_path": null
}
```

Fields:

- `program`: program to debug.
- `args`: program arguments array.
- `cwd`: debuggee working directory.
- `env`: environment variables.
- `stopAtEntry`: request an entry stop.
- `gdbPath`: GDB executable path.
- `rpc_transport`: `auto`, `unix`, or `tcp`.
- `rpc_host`: TCP RPC host.
- `rpc_port`: TCP RPC port.
- `rpc_socket_path`: Unix socket path.

## AI Assistant Beta Configuration

AI Assistant support currently includes a safe configuration layer, a read-only
Debug context collection layer, prompt builders, an offline Mock AI analysis
service, and an OpenAI-compatible Provider implementation at the internal
provider/service layer. HTTP/RPC endpoints and Neovim commands are connected,
so the AI beta flow is end-to-end for manual validation. AI is disabled by
default, and Magic Debug will not call an external AI API unless the user
explicitly enables AI and configures a provider.

Recommended environment variables:

```bash
export MAGIC_DEBUG_AI_ENABLED=true
export MAGIC_DEBUG_AI_PROVIDER=openai-compatible
export MAGIC_DEBUG_AI_MODEL=your-model
export MAGIC_DEBUG_AI_BASE_URL=https://api.example.com/v1
export MAGIC_DEBUG_AI_API_KEY=...
```

Configuration file example:

```json
{
  "ai": {
    "enabled": false,
    "provider": "openai-compatible",
    "model": "",
    "base_url": "",
    "api_key": "",
    "timeout": 30,
    "max_context_chars": 12000,
    "include_source": false,
    "include_variables": false,
    "include_stack": true,
    "include_breakpoints": true
  }
}
```

API keys are intended to come from environment variables such as
`MAGIC_DEBUG_AI_API_KEY`; do not commit real keys to `magic-debug.json`.
The safe config representation masks API keys. By default, AI context options do
not include source text or variable values:

- `include_source=false`
- `include_variables=false`

The Debug context builder can collect the current debug status, stopped reason,
stack summary, breakpoint summary, recent error, and launch information without
sending DAP requests or changing debugger state. Source snippets and variable
summaries are opt-in with:

- `include_source=true`
- `include_variables=true`

Collected context is capped by `max_context_chars` and may be truncated before a
future prompt layer receives it.

The Prompt builder can prepare debug analysis, error explanation, and suggested
next-step prompts from the redacted Debug context. The Mock AI provider is for
offline tests only; it is deterministic and has no network access.

The OpenAI-compatible Provider uses Chat Completions style requests with
`model`, `base_url`, `api_key`, and `timeout` from configuration. API keys should
be provided through `MAGIC_DEBUG_AI_API_KEY`; tests use mocked network calls and
do not access real external services.

For offline local validation, use the mock provider:

```json
{
  "ai": {
    "enabled": true,
    "provider": "mock",
    "model": "mock-debugger",
    "base_url": "mock://local",
    "api_key": "local-test"
  }
}
```

HTTP AI endpoints are available from the backend:

- `GET /api/ai/config`
- `POST /api/ai/config`
- `POST /api/ai/analyze`
- `POST /api/ai/explain-error`
- `POST /api/ai/suggest-next-step`

Example HTTP analysis request:

```json
{
  "question": "Why did the program stop here?"
}
```

RPC AI methods are available with the same response/error envelope as other RPC
calls:

- `ai.getConfig`
- `ai.updateConfig`
- `ai.analyze`
- `ai.explainError`
- `ai.suggestNextStep`

Neovim AI commands call those backend RPC methods:

- `:MagicDebugAIConfig`
- `:MagicDebugAIConfig enable-mock`
- `:MagicDebugAIAnalyze Why did the program stop here?`
- `:MagicDebugAIExplainError Segmentation fault`
- `:MagicDebugAISuggestNextStep`

The Neovim plugin does not call OpenAI-compatible providers directly. It only
talks to the Magic Debug backend over RPC and displays the backend response in a
floating window or logs buffer.

Config responses mask API keys as `***`; they never return the plain API key.
Runtime config updates are in-memory for the current server process. For
persistent configuration, use environment variables or `magic-debug.json`.
When `openai-compatible` is enabled, the selected Debug context is sent to the
configured `base_url`. The mock provider does not access the network.

Current user-facing AI limitations:

- Magic Debug does not automatically execute debug commands.
- Magic Debug does not automatically modify source code.
- Source snippets and variable values remain disabled by default.
- AI output is advisory.

For release validation and privacy checks, see
[docs/ai-beta-validation.md](docs/ai-beta-validation.md).

## RPC Transport

`auto`:

- Linux/macOS resolves to Unix Domain Socket.
- If POSIX Unix socket creation fails, the server can fallback to TCP and logs a
  warning.

`unix`:

- Uses Unix Domain Socket.
- Configure with `--rpc-socket`.

`tcp`:

- Uses host/port.
- Default endpoint is `127.0.0.1:8766`.
- Useful for local troubleshooting, port forwarding, and cross-process
  connections on supported platforms.

CLI examples:

```bash
magic-debug --rpc --rpc-transport auto
magic-debug --rpc --rpc-transport tcp --rpc-host 127.0.0.1 --rpc-port 8766
magic-debug --rpc --rpc-transport unix --rpc-socket /tmp/magic-debug.sock
```

TCP plugin example:

```lua
require("magic-debug").setup({
  rpc_transport = "tcp",
  rpc_host = "127.0.0.1",
  rpc_port = 8766,
  server_command = {
    "magic-debug",
    "--rpc",
    "--rpc-transport",
    "tcp",
    "--rpc-host",
    "127.0.0.1",
    "--rpc-port",
    "8766",
  },
})
```

Windows is not part of the official beta support matrix. Named Pipe support is
not implemented.

## Doctor And Check

Human-readable diagnostics:

```bash
magic-debug doctor
```

Machine-readable diagnostics:

```bash
magic-debug --check --json
```

Exit codes:

- `0`: ok
- `1`: warn
- `2`: error

Common warnings:

- `gdb` is not installed.
- `gdb --interpreter=dap` appears unavailable.
- A default port is already in use.

Common errors:

- Log directory is not writable.
- Python version is incompatible.
- RPC transport cannot be resolved.

JSON output is intended for CI and deployment scripts.

## HTTP And RPC API Overview

HTTP success responses use:

```json
{"success": true, "data": {}}
```

HTTP errors use status codes plus:

```json
{
  "success": false,
  "error": {
    "code": "INVALID_STATE",
    "message": "Human readable message",
    "details": {}
  }
}
```

RPC responses are line-delimited JSON:

```json
{"type": "response", "id": 1, "success": true, "result": {}}
```

RPC events are distinct from responses:

```json
{"type": "event", "event": "stopped", "body": {}}
```

## Testing

Run the standard suite:

```bash
python -c "from adapters.gdb import *"
python -c "import main"
pytest tests/ -q
python -m compileall core adapters server main.py tests
```

Run real GDB DAP e2e only:

```bash
pytest tests/test_e2e_gdb_dap.py -q -rs
```

If `gcc`, `gdb`, or `gdb --interpreter=dap` is missing, the real e2e test is
skipped. That is expected. The fake DAP process test still runs and covers the
response/event flow without real GDB.

## Build And Packaging

```bash
python -m pip install build
python -m build
python -m pip install dist/*.whl
magic-debug --help
magic-debug --check --json
```

## Beta Validation

Before tagging a beta release, run the manual checklist in
[docs/beta-checklist.md](docs/beta-checklist.md). See
[RELEASE_NOTES.md](RELEASE_NOTES.md) for the `v0.1.0-beta` draft and
[CHANGELOG.md](CHANGELOG.md) for the change summary.

## Troubleshooting

### gdb not found

Run:

```bash
magic-debug doctor
```

Install GDB and set `gdbPath` if it is not on `PATH`.

### gdb --interpreter=dap not available

Upgrade GDB or use a distribution build that includes DAP support. The real e2e
test may skip when DAP is unavailable.

### RPC connection failed

- Open `:MagicDebugLogs`.
- Check `--rpc-transport`.
- On Linux/macOS, check the socket path.
- Try `--rpc-transport tcp`.

### Port already in use

Run `magic-debug doctor`, then change `--rpc-port` or `--port`.

### Unix socket stale

Check the socket path. Magic Debug refuses to delete a regular file at the socket
path. Remove only a confirmed stale socket.

### Neovim plugin cannot start the server

Use array-form `server_command`, for example:

```lua
server_command = { "magic-debug", "--rpc" }
```

Then inspect `:MagicDebugLogs`.

### Breakpoint not hit

- Compile with `-g -O0`.
- Use a source path that GDB can match, preferably an absolute path.
- Confirm `configurationDone` and `continue` have run.

## Current Limitations

- Current backend focus is GDB DAP, not LLDB.
- `runInTerminal` is not implemented and returns a clear unsupported error.
- The Neovim UI is intentionally minimal and is not a full IDE-style panel set.
- Real e2e tests require GCC plus GDB DAP and skip when unavailable.
- Windows is not part of the official beta support matrix.
- Python 3.8 and 3.9 are not supported.
- Windows Named Pipe support is not implemented.
- GDB DAP launch parameters can vary by GDB version.
- Full variable tree UI, complex thread UI, AI debugging assistant behavior, and
  remote team workflows are not currently promised.

## Development Roadmap

- Phase 2: richer Neovim UI panels.
- Phase 3: fuller variables, threads, and stack interaction.
- Phase 4: stable beta release and PyPI publishing.
- Phase 5: optional AI debugging assistant integration.

## License

MIT License. See [LICENSE](LICENSE).
