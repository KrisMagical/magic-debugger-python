import json
import urllib.error
import urllib.request

from .config import AIConfig


class AIProviderError(Exception):
    pass


class BaseAIProvider:
    def analyze(self, messages: list[dict[str, str]], config: AIConfig) -> str:
        raise NotImplementedError


def _redact_secret(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "***")


def _validate_messages(messages: list[dict[str, str]]) -> None:
    if not messages or not isinstance(messages, list):
        raise AIProviderError("AI messages must be a non-empty list of dictionaries")
    if not all(isinstance(message, dict) for message in messages):
        raise AIProviderError("AI messages must be a non-empty list of dictionaries")
    if not all(
        message.get("role") and isinstance(message.get("content"), str)
        for message in messages
    ):
        raise AIProviderError("AI messages must include role and string content")


class MockAIProvider(BaseAIProvider):
    def analyze(self, messages: list[dict[str, str]], config: AIConfig) -> str:
        _validate_messages(messages)
        combined = "\n".join(message["content"] for message in messages)
        task_line = next(
            (line for line in combined.splitlines() if line.startswith("Task:")),
            "Task: Analyze the current debugging state.",
        )
        status = "unknown"
        if '"status":' in combined:
            marker = '"status":'
            tail = combined.split(marker, 1)[1].strip()
            if tail.startswith('"'):
                status = tail.split('"', 2)[1]

        return "\n".join(
            [
                "Mock AI Analysis",
                f"Summary: Offline mock analysis for {task_line.removeprefix('Task:').strip()}",
                f"Observed status: {status}",
                "Likely cause: Review the stopped frame, breakpoints, and recent error in the provided context.",
                "Evidence from context: This response is based only on the supplied prompt messages.",
                "Suggested next steps:",
                "- Inspect the top stack frame.",
                "- Review relevant breakpoints.",
                "- Collect variables or source snippets only if explicitly enabled.",
                "Commands to try: step, continue, stackTrace, variables, or add a focused breakpoint.",
                "Confidence: low (mock provider, no real AI model).",
            ]
        )


class OpenAICompatibleProvider(BaseAIProvider):
    def analyze(self, messages: list[dict[str, str]], config: AIConfig) -> str:
        self._validate_config(config)
        _validate_messages(messages)

        url = f"{config.base_url.rstrip('/')}/chat/completions"
        body = json.dumps(
            {
                "model": config.model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 800,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                raw_body = response.read()
        except urllib.error.HTTPError as exc:
            raise AIProviderError(self._format_http_error(exc, config.api_key)) from exc
        except urllib.error.URLError as exc:
            message = _redact_secret(
                f"AI provider network error: {exc.reason}", config.api_key
            )
            raise AIProviderError(message) from exc
        except OSError as exc:
            message = _redact_secret(
                f"AI provider request failed: {exc}", config.api_key
            )
            raise AIProviderError(message) from exc

        return self._parse_response(raw_body, config.api_key)

    @staticmethod
    def _validate_config(config: AIConfig) -> None:
        if not config.api_key:
            raise AIProviderError("AI API key is not configured")
        if not config.base_url:
            raise AIProviderError("AI base URL is not configured")
        if not config.model:
            raise AIProviderError("AI model is not configured")

    @staticmethod
    def _format_http_error(exc: urllib.error.HTTPError, api_key: str) -> str:
        try:
            body_preview = exc.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            body_preview = "<unable to read error body>"
        return _redact_secret(
            f"AI provider HTTP error {exc.code}: {body_preview}", api_key
        )

    @staticmethod
    def _parse_response(raw_body: bytes, api_key: str) -> str:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AIProviderError("AI provider returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise AIProviderError("AI provider response must be a JSON object")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIProviderError("AI provider response did not include choices")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise AIProviderError("AI provider choice must be a JSON object")

        message = first_choice.get("message")
        content = None
        if isinstance(message, dict):
            content = message.get("content")
        if content is None:
            content = first_choice.get("text")

        if not isinstance(content, str):
            raise AIProviderError("AI provider response did not include message content")

        content = _redact_secret(content.strip(), api_key)
        if not content:
            raise AIProviderError("AI provider response content was empty")
        return content
