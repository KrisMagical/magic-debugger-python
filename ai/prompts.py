import json

from .context import DebugAIContext


SYSTEM_PROMPT = """You are Magic Debug Assistant.

You must only analyze the provided Debug Context.
Do not invent stack frames, variables, source code, logs, commands, or program state.
Do not claim that you executed debugger commands.
Do not automatically execute debug commands.
Do not automatically modify source code.
Suggest possible next steps the user can try manually.
If the context is insufficient, say what additional context is needed.
Your output is advisory and may be wrong; keep confidence calibrated.
"""


ANSWER_FORMAT = """Please answer with:
- Summary
- Likely cause
- Evidence from context
- Suggested next steps
- Commands to try
- Confidence
"""


def _context_json(context: DebugAIContext) -> str:
    return json.dumps(context.to_prompt_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _messages(task: str, context: DebugAIContext, extra: str | None = None) -> list[dict[str, str]]:
    parts = [
        f"Task: {task}",
        "Debug Context:",
        _context_json(context),
    ]
    if extra:
        parts.extend(["Additional user input:", extra])
    parts.append(ANSWER_FORMAT)
    return [
        {"role": "system", "content": SYSTEM_PROMPT.strip()},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def build_debug_analysis_prompt(
    context: DebugAIContext,
    user_question: str | None = None,
) -> list[dict[str, str]]:
    return _messages("Analyze the current debugging state.", context, user_question)


def build_explain_error_prompt(
    context: DebugAIContext,
    error_message: str | None = None,
) -> list[dict[str, str]]:
    extra = f"Error message: {error_message}" if error_message else None
    return _messages("Explain the error using the current debugging state.", context, extra)


def build_next_step_prompt(
    context: DebugAIContext,
) -> list[dict[str, str]]:
    return _messages("Suggest the next debugging step.", context)
