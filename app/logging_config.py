"""Registros en JSON: request.log (todas las solicitudes) y error.log (errores)."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

request_logger = logging.getLogger("trama.request")
error_logger = logging.getLogger("trama.error")


class JsonFormatter(logging.Formatter):
    """Una línea JSON por registro. Los campos van en `extra={"data": {...}}`."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            **getattr(record, "data", {}),
        }
        if record.exc_info:
            entry["traceback"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(log_dir: str) -> None:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    for logger, filename in ((request_logger, "request.log"), (error_logger, "error.log")):
        # create_app puede llamarse más de una vez (tests): no duplicar handlers.
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        handler = logging.FileHandler(path / filename, encoding="utf-8")
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
