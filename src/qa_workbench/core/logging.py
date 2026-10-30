"""Safe application logging setup."""

import logging
import re
import sys
from pathlib import Path

from qa_workbench.core.config import AppConfig

_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)"
    r"(\s*[:=]\s*|\s+)([^\s,;]+)"
)


class SecretRedactionFilter(logging.Filter):
    """Mask common secret-like values in log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _SECRET_PATTERN.sub(r"\1=***", str(record.getMessage()))
        record.args = ()
        return True


def configure_logging(config: AppConfig) -> None:
    """Configure console logging and an optional file handler."""
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
    ]
    if config.log_file is not None:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(config.log_file, encoding="utf-8"))

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    redaction = SecretRedactionFilter()
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(redaction)

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        handlers=handlers,
        force=True,
    )
