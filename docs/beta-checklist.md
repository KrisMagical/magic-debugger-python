# Beta Validation Checklist

Use this checklist before creating a `v0.1.0-beta` release. Record the exact
environment and command results; do not treat missing `gdb` on a development
machine as a packaging failure.

## Environment

Record:

- Python version: 3.10 / 3.11 / 3.12
- OS: Linux / macOS
- GDB version:
- GCC version:
- Neovim version, if testing the plugin:
- RPC transport used: `auto` / `unix` / `tcp`
- Notes:

Required validation platforms:

- Linux
- macOS

Required Python versions:

- 3.10
- 3.11
- 3.12

## Core Smoke Test

```bash
python -c "from adapters.gdb import *"
python -c "import main"
pytest tests/ -q
python -m compileall core adapters server main.py tests
```

Expected result:

- Imports pass.
- Test suite passes.
- Real GDB DAP e2e may skip when `gcc`, `gdb`, or GDB DAP support is missing.

## Doctor / Check

```bash
magic-debug doctor
magic-debug --check --json
```

Exit codes:

- `0` = ok
- `1` = warn
- `2` = error

Warnings such as missing `gdb` are acceptable on machines that are not intended
to run real debugging. Beta release validation should include at least one real
debugging machine.

## GDB DAP E2E

On a real Linux or macOS environment with GCC or Clang and GDB installed:

```bash
gcc --version
gdb --version
gdb --interpreter=dap --version
pytest tests/test_e2e_gdb_dap.py -q -rs
```

Expected result:

- With GCC, GDB, and GDB DAP support: test should complete initialize,
  setBreakpoints, launch, configurationDone, continue/stopped, and stackTrace.
- Without that environment: skip is reasonable.

## Wheel Validation

```bash
python -m build
python -m pip install --force-reinstall dist/*.whl
magic-debug --help
magic-debug doctor
```

Clean virtual environment option:

```bash
python -m venv .venv-release
. .venv-release/bin/activate
python -m pip install --upgrade pip
python -m pip install dist/*.whl
magic-debug --help
```

## Minimal C Sample

```bash
gcc -g -O0 tests/fixtures/test_sample.c -o /tmp/test_sample
magic-debug doctor
magic-debug --rpc --rpc-transport auto
```

Expected result:

- Backend starts.
- `doctor` has no blocking errors.
- Missing `gdb` should be fixed before real debugging validation.

## Neovim Plugin Smoke

Add the plugin to runtimepath:

```lua
vim.opt.rtp:append("/path/to/magic-debugger-python-main/vim-plugin")
require("magic-debug").setup({
  rpc_transport = "auto",
  server_command = { "magic-debug", "--rpc", "--rpc-transport", "auto" },
})
```

Run:

```vim
:MagicDebugStart /tmp/test_sample
:MagicDebugToggleBreakpoint
:MagicDebugContinue
:MagicDebugLogs
:MagicDebugReconnect
```

Expected result:

- Plugin connects to the backend.
- Logs are visible with `:MagicDebugLogs`.
- Response and event messages do not interfere with each other.

## Optional Future Validation

Windows is not part of the `v0.1.0-beta` official support matrix. TCP transport
may be useful for future Windows experiments, but Windows should not block this
beta release.

## Pass / Fail Table

| Check | Result | Notes |
|---|---|---|
| Linux pytest | pass/fail/skip | |
| macOS pytest | pass/fail/skip | |
| Python 3.10 | pass/fail | |
| Python 3.11 | pass/fail | |
| Python 3.12 | pass/fail | |
| compileall | pass/fail | |
| doctor | ok/warn/error | |
| check JSON | ok/warn/error | |
| e2e GDB DAP on Linux/macOS | pass/fail/skip | |
| wheel build | pass/fail | |
| wheel install | pass/fail | |
| minimal C sample | pass/fail/not tested | |
| Neovim plugin | pass/fail/not tested | |
