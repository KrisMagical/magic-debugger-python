# Changelog

## v0.1.0-beta - Unreleased

### Added

- GDB DAP backend validation around `gdb --interpreter=dap`.
- `magic-debug doctor` and `magic-debug --check --json`.
- RPC transport modes: `auto`, `unix`, and `tcp`.
- Linux/macOS Unix socket default for RPC auto mode.
- HTTP/RPC structured error payloads.
- Neovim RPC request id, pending request, and response/event dispatch.
- Neovim commands `:MagicDebugLogs` and `:MagicDebugReconnect`.
- `magic-debug.json` / `.magic-debug.json` launch config lookup.
- Real GDB DAP e2e test entry.
- Fake DAP process test coverage.
- Packaging workflows and wheel/sdist validation.
- Beta validation checklist and release notes draft.
- AI Assistant configuration model with safe API key masking.
- AI debug context collection layer with privacy-safe defaults.
- AI prompt builder for debug analysis, error explanation, and next-step
  suggestions.
- Mock AI provider for offline tests.
- AIAnalysisService with disabled-by-default behavior.
- OpenAI-compatible AI provider implementation using stdlib `urllib`.
- Provider error handling and API key redaction for AI API failures.
- HTTP AI endpoints for config, analyze, explain-error, and suggest-next-step.
- RPC AI methods for config and analysis.
- AI API responses use safe config output and keep AI disabled by default.
- Neovim AI commands for config, analyze, explain-error, and suggest-next-step.
- AI result display and error handling in the Neovim plugin.
- AI Debug Assistant Beta end-to-end flow.
- AI validation checklist.
- Neovim AI command smoke instructions.

### Fixed

- Dataclass `field(default_fault=list)` typo in the GDB adapter.
- LLDB naming leftovers in project metadata and deployment checks.
- DAP `Content-Length` now uses UTF-8 byte length.
- DAP stdin/stdout now use binary streams rather than text mode.
- DAP stdout body reads no longer rely on `readline()`.
- `DebugController.start()` no longer clears pre-set breakpoints.
- `configurationDone` no longer forces the state to `RUNNING`.
- `current_thread_id` and `current_frame_id` now start as `None`.
- Step commands no longer send `threadId=0`.
- Continue requests no longer send `threadId=0`.
- `runInTerminal` no longer returns fake success.
- HTTP errors no longer default to `200 + success:false`.
- RPC failures are returned in `error`, not nested inside `result`.
- Neovim server startup no longer uses shell background concatenation.

### Changed

- README rewritten for the current GDB DAP beta.
- Official beta support target is Linux/macOS with Python 3.10-3.12.
- Removed Windows from the official CI/support matrix.
- Removed Python 3.8 and 3.9 from the official support matrix.
- Windows validation is deferred.
- `setup.py` reduced to a compatibility shim.
- `pyproject.toml` metadata improved and console script verified.
- `config.example.json` updated to current launch and RPC transport fields.
- `start.sh` and `Makefile` use doctor/check style validation.

### Known Limitations

- `runInTerminal` is unsupported.
- Neovim UI remains lightweight and is not a full IDE-style panel set.
- Windows is not part of the official beta support matrix.
- Python 3.8 and 3.9 are not supported.
- Named Pipe support is not implemented.
- GDB DAP behavior may vary by version and distribution.
- Full variable/thread UI is not complete in this beta.
- External AI API usage requires explicit user configuration.
- AI output is advisory and does not execute debugger commands or modify source.
- Real GDB DAP validation requires GCC plus a GDB build with DAP support.

### Security / Privacy

- AI is disabled by default.
- API keys are masked in config responses and logs.
- Source and variable context are disabled by default.
- AI output is advisory and does not execute debugger commands or modify source.
