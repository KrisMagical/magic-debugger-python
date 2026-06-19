# Magic Debug v0.1.0-beta

## Summary

Magic Debug is a Linux/macOS GDB DAP debugger backend and Vim/Neovim
integration with opt-in AI-assisted debug analysis.

This beta targets Python 3.10-3.12 and GDB with `gdb --interpreter=dap`.
Windows is not part of the official beta support matrix.

## Install

Install from a built wheel:

```bash
python -m pip install dist/*.whl
```

Install from source for development:

```bash
python -m pip install -e .
```

## Highlights

- GDB DAP backend based on `gdb --interpreter=dap`.
- Reliable DAP byte framing.
- DebugController lifecycle fixes.
- HTTP/RPC structured error model.
- Neovim RPC request/response/event dispatch.
- RPC transport modes: `auto`, `unix`, and `tcp`.
- `magic-debug doctor` and `magic-debug --check --json`.
- Wheel and sdist packaging.
- Real GDB DAP e2e test entry with graceful skip when gcc/gdb/DAP support is
  unavailable.
- AI Debug Assistant Beta:
  - AIConfig and privacy-safe defaults.
  - Debug context collection.
  - Prompt builder.
  - Mock provider for offline validation.
  - OpenAI-compatible provider for explicit opt-in usage.
  - HTTP/RPC AI endpoints.
  - Neovim AI commands.

## Validation

```bash
python -c "from adapters.gdb import *"
python -c "import main"
pytest tests/ -q
python -m compileall ai core adapters server main.py tests scripts
python main.py --help
python scripts/ci_check_diagnostics.py
python -m build
```

Optional real GDB DAP validation:

```bash
pytest tests/test_e2e_gdb_dap.py -q -rs
```

Mock AI validation:

```vim
:MagicDebugAIConfig enable-mock
:MagicDebugAIAnalyze Why did it stop here?
:MagicDebugAISuggestNextStep
:MagicDebugLogs
```

## AI Privacy Defaults

- AI is disabled by default.
- API keys are masked in config responses.
- Source snippets are disabled by default.
- Variable values are disabled by default.
- The Neovim plugin only calls the backend over RPC; it does not call providers
  directly.
- Magic Debug does not automatically execute debugger commands.
- Magic Debug does not automatically modify source code.
- OpenAI-compatible provider usage requires explicit user configuration.

## Known Limitations

- Linux/macOS are the official beta support targets.
- Windows is not officially supported in this beta.
- `runInTerminal` is unsupported.
- Neovim UI is lightweight and not a full IDE panel set.
- GDB DAP behavior may vary by GDB version and distribution.
- Named Pipe support is not implemented.
- Full variable/thread UI is not complete.
- Real OpenAI-compatible validation is optional and should be run manually with
  explicit user consent.

## Feedback Wanted

Please include:

- OS and version.
- Python version.
- GDB version.
- Neovim version.
- RPC transport.
- `magic-debug doctor` or `magic-debug --check --json` output.
- AI provider type: `mock` or `openai-compatible`.
- Relevant logs with API keys removed.
