"""Shared HTTP/RPC error response helpers."""

from typing import Any, Dict, Optional, Tuple


ERROR_STATUS = {
    "BAD_REQUEST": 400,
    "NOT_FOUND": 404,
    "INVALID_STATE": 409,
    "CONFLICT": 409,
    "TIMEOUT": 504,
    "NOT_IMPLEMENTED": 501,
    "METHOD_NOT_FOUND": 404,
    "INTERNAL_ERROR": 500,
}


class APIError(Exception):
    """Exception carrying a stable API error code."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status: Optional[int] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status or status_for_error(code)


def error_payload(
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def success_payload(data: Any = None) -> Dict[str, Any]:
    return {
        "success": True,
        "data": data,
    }


def status_for_error(code: str) -> int:
    return ERROR_STATUS.get(code, 500)


def normalize_error(error: Any, default_code: str = "INVALID_STATE") -> Dict[str, Any]:
    if isinstance(error, dict):
        code = str(error.get("code") or default_code)
        message = str(error.get("message") or code)
        details = error.get("details") or {}
        return error_payload(code, message, details)["error"]

    message = str(error or "Request failed")
    return error_payload(infer_error_code(message, default_code), message)["error"]


def infer_error_code(message: str, default_code: str = "INVALID_STATE") -> str:
    lower = message.lower()
    if "missing" in lower or "invalid" in lower or "parameter" in lower:
        return "BAD_REQUEST"
    if "not found" in lower:
        return "NOT_FOUND"
    if "timeout" in lower or "timed out" in lower:
        return "TIMEOUT"
    if "not implemented" in lower or "unsupported" in lower:
        return "NOT_IMPLEMENTED"
    if (
        "not running" in lower
        or "not stopped" in lower
        or "not started" in lower
        or "no active" in lower
        or "cannot" in lower
        or "failed" in lower
    ):
        return "INVALID_STATE"
    return default_code


def exception_to_error(exc: Exception) -> Tuple[int, Dict[str, Any]]:
    if isinstance(exc, APIError):
        return exc.status, error_payload(exc.code, exc.message, exc.details)
    if isinstance(exc, ValueError):
        return 400, error_payload("BAD_REQUEST", str(exc))
    if isinstance(exc, FileNotFoundError):
        return 404, error_payload("NOT_FOUND", str(exc))
    if isinstance(exc, TimeoutError):
        return 504, error_payload("TIMEOUT", str(exc))
    return 500, error_payload("INTERNAL_ERROR", "Internal server error")


def normalize_controller_result(result: Any) -> Tuple[int, Dict[str, Any]]:
    """Convert legacy controller-style results into stable API payloads."""
    if isinstance(result, tuple) and len(result) == 2:
        status, payload = result
        if isinstance(payload, dict) and payload.get("success") is False:
            return int(status), error_payload_from_result(payload)
        return int(status), payload

    if isinstance(result, dict) and result.get("success") is False:
        payload = error_payload_from_result(result)
        return status_for_error(payload["error"]["code"]), payload

    if isinstance(result, dict) and result.get("success") is True:
        return 200, result

    return 200, success_payload(result)


def error_payload_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    raw_error = result.get("error") or result.get("message") or "Request failed"
    error = normalize_error(raw_error)
    return error_payload(error["code"], error["message"], error["details"])
