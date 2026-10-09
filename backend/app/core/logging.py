import json
import logging
from datetime import datetime, timezone
from .errors import redact


class JSONFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": redact(record.getMessage()),
        }
        for field in ("task_id", "project_id", "provider", "duration_ms", "error_type"):
            if hasattr(record, field):
                data[field] = getattr(record, field)
        return json.dumps(data, ensure_ascii=False)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger("cineai")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
