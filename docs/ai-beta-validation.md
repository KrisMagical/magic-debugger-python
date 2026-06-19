# AI Debug Assistant Beta Validation

Use this checklist for manual validation before publishing an AI Debug Assistant
beta. Do not put real API keys in issues, screenshots, logs, or test fixtures.

## Scope

Current AI beta support includes:

- AI configuration from environment variables and runtime API updates.
- Debug context collection from the current controller state.
- Prompt builders for debug analysis, error explanation, and next-step advice.
- Offline Mock provider.
- OpenAI-compatible provider.
- HTTP/RPC AI endpoints.
- Neovim AI commands.

Current AI beta support does not include:

- AI automatically executing debugger commands.
- AI automatically modifying source code.
- Long-term memory.
- A complex multi-turn chat UI.
- Source code upload by default.
- Variable value upload by default.

## Supported Environment

- Linux / macOS.
- Python 3.10-3.12.
- GDB with `gdb --interpreter=dap`.
- Neovim for plugin smoke validation.
- Windows is not officially supported in this beta.

## Privacy Defaults

- AI is disabled by default.
- API keys are never returned in plain text by config endpoints.
- Source code is not included by default.
- Variable values are not included by default.
- Stack and breakpoints may be included as context summaries by default.
- If the user enables the `openai-compatible` provider, the allowed debug
  context is sent to the configured `base_url`.
- Validate the flow with the mock provider before using a real provider.

## Mock Provider Validation

Start the backend:

```bash
magic-debug --rpc --rpc-transport auto
```

In Neovim:

```vim
:MagicDebugAIConfig
:MagicDebugAIConfig enable-mock
:MagicDebugAIAnalyze Why did it stop here?
:MagicDebugAIExplainError Segmentation fault
:MagicDebugAISuggestNextStep
:MagicDebugLogs
```

Expected result:

- Mock analysis output is shown.
- No real network access is required.
- API keys are not displayed.
- Debug commands are not executed automatically.
- Source files are not modified.
- Failures display `error.message`.

## HTTP Mock Validation

Configure the mock provider:

```http
POST /api/ai/config
Content-Type: application/json

{
  "enabled": true,
  "provider": "mock",
  "model": "mock-debugger",
  "base_url": "mock://local",
  "api_key": "local-test"
}
```

Run analysis:

```http
POST /api/ai/analyze
Content-Type: application/json

{
  "question": "Why did the program stop here?"
}
```

Expected result:

- `success=true`.
- `data.analysis` exists.
- The response does not contain the plain API key.

## RPC Mock Validation

Validate these RPC methods:

- `ai.getConfig`
- `ai.updateConfig`
- `ai.analyze`
- `ai.explainError`
- `ai.suggestNextStep`

Expected result:

- Responses have `type=response`.
- Successful responses use `result`.
- Failed responses use `error`.
- Failed responses do not put failures inside `result`.
- Responses do not contain the plain API key.

## OpenAI-Compatible Provider Optional Validation

This step is optional and must be run manually with explicit user consent. It is
not a CI requirement and should not run in automated tests.

```bash
export MAGIC_DEBUG_AI_ENABLED=true
export MAGIC_DEBUG_AI_PROVIDER=openai-compatible
export MAGIC_DEBUG_AI_MODEL=your-model
export MAGIC_DEBUG_AI_BASE_URL=https://api.example.com/v1
export MAGIC_DEBUG_AI_API_KEY=...
```

Recommended first pass:

- Keep `include_source=false`.
- Keep `include_variables=false`.
- Run `:MagicDebugAIAnalyze Why did the program stop here?`.

Expected result:

- Analysis is returned when the provider is configured correctly.
- Provider failures display `error.message`.
- API keys do not appear in logs, responses, issues, or screenshots.
- Missing `base_url`, `model`, or `api_key` returns `AI_CONFIG_ERROR` or
  `AI_PROVIDER_ERROR`.

## Failure Path Validation

Validate these paths:

- AI disabled.
- Missing API key.
- Missing model.
- Missing base URL.
- Provider HTTP error.
- Provider invalid JSON.
- RPC disconnected.
- Neovim server not running.
- Context too large / truncated.

## Pass / Fail Table

| Check | Result | Notes |
|---|---|---|
| AI disabled error | pass/fail | |
| Mock provider HTTP | pass/fail | |
| Mock provider RPC | pass/fail | |
| Neovim AI mock | pass/fail | |
| API key masking | pass/fail | |
| OpenAI-compatible optional | pass/fail/not tested | |
| No auto execution | pass/fail | |
| No source by default | pass/fail | |
| No variables by default | pass/fail | |
