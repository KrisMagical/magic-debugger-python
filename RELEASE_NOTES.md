# Magic Debug v0.1.0-beta Release Notes

Status: draft for beta validation.

Official beta support:

- Linux
- macOS
- Python 3.10-3.12

Not officially supported:

- Windows
- Python 3.8 / 3.9

## Highlights

- GDB DAP backend based on `gdb --interpreter=dap`.
- Reliable Debug Adapter Protocol byte framing.
- DebugController lifecycle fixes for breakpoints, stopped state, and thread ids.
- Stable HTTP/RPC error model.
- Neovim RPC response/event dispatch using request ids and pending requests.
- RPC transport modes: `auto`, `unix`, and `tcp`.
- `magic-debug doctor` and `magic-debug --check --json` diagnostics.
- Wheel/sdist packaging and console script validation.
- Real GDB DAP e2e test entry with graceful skip when the environment is absent.

## What Works

- Import and CLI smoke checks.
- DAP framing tests, including non-ASCII payloads.
- Fake DAP process tests for response/event flow.
- GDB DAP e2e when GCC, GDB, and GDB DAP support are available.
- RPC TCP/Unix endpoint resolution.
- Basic Neovim plugin commands and logs.
- HTTP/RPC structured errors.
- Doctor/check diagnostics.
- Wheel and source distribution builds.

## Known Limitations

- `runInTerminal` is unsupported and returns a clear error.
- Neovim UI is still lightweight; it is not a full IDE-style debug panel.
- Windows is not part of the official beta support matrix.
- Python 3.8 and 3.9 are not supported.
- Named Pipe support is not implemented.
- GDB DAP behavior may vary by GDB version and distribution.
- Full variable/thread UI is not complete in this beta.
- No AI debugging assistant behavior is included in this beta.
- No final PyPI release should happen until real Linux + GDB DAP + Neovim
  validation has been completed.

## Validation Commands

```bash
python -c "from adapters.gdb import *"
python -c "import main"
pytest tests/ -q
pytest tests/test_e2e_gdb_dap.py -q -rs
python -m compileall core adapters server main.py tests
magic-debug doctor
magic-debug --check --json
python -m build
```

On a real Linux or macOS validation host:

```bash
gcc --version
gdb --version
gdb --interpreter=dap --version
pytest tests/test_e2e_gdb_dap.py -q -rs
```

## Upgrade / Install

Development install:

```bash
python -m pip install -e .
```

Build and install wheel:

```bash
python -m pip install build
python -m build
python -m pip install --force-reinstall dist/*.whl
magic-debug --help
magic-debug doctor
```

## Feedback Wanted

Please include the following with bug reports:

- OS and version.
- Python version.
- GDB version.
- Output of `gdb --interpreter=dap --version`.
- Neovim version, if relevant.
- RPC transport used.
- `magic-debug --check --json` output.
- `:MagicDebugLogs` output for plugin failures.
- Minimal source file or reproduction steps.
