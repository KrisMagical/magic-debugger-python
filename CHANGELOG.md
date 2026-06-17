# Changelog

## v0.1.0-beta - Unreleased

### Added

- GDB DAP backend validation around `gdb --interpreter=dap`.
- `magic-debug doctor` and `magic-debug --check --json`.
- RPC transport modes: `auto`, `unix`, and `tcp`.
- Windows TCP default for RPC auto mode.
- Linux/macOS Unix socket default for RPC auto mode.
- HTTP/RPC structured error payloads.
- Neovim RPC request id, pending request, and response/event dispatch.
- Neovim commands `:MagicDebugLogs` and `:MagicDebugReconnect`.
- `magic-debug.json` / `.magic-debug.json` launch config lookup.
- Real GDB DAP e2e test entry.
- Fake DAP process test coverage.
- Packaging workflows and wheel/sdist validation.
- Beta validation checklist and release notes draft.

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
- `setup.py` reduced to a compatibility shim.
- `pyproject.toml` metadata improved and console script verified.
- `config.example.json` updated to current launch and RPC transport fields.
- `start.sh` and `Makefile` use doctor/check style validation.

### Known Limitations

- `runInTerminal` is unsupported.
- Neovim UI remains lightweight and is not a full IDE-style panel set.
- Windows uses TCP by default; Named Pipe support is not implemented.
- GDB DAP behavior may vary by version and distribution.
- Full variable/thread UI is not complete in this beta.
- No AI debugging assistant behavior is included in this beta.
- Real GDB DAP validation requires GCC plus a GDB build with DAP support.
