import re


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details or {}


class TransientProviderError(AppError):
    pass


class Cancelled(Exception):
    pass


def safe_error(exc):
    # Provider payloads/headers are never exposed. Internal errors stay generic.
    return exc.message if isinstance(exc, AppError) else "任务执行失败，请检查服务日志与配置"


def redact(value):
    return re.sub(r"(sk-[\w-]+|Bearer\s+\S+|SecretKey[=:]\s*\S+)", "[REDACTED]", str(value))[:1000]
