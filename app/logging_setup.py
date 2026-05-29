import logging
from collections import deque
from typing import Deque, List

# Store the most recent log entries in memory. Adjust maxlen as needed.
log_buffer: Deque[str] = deque(maxlen=500)

class InMemoryLogHandler(logging.Handler):
    """Logging handler that appends formatted log records to an in‑memory buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        log_buffer.append(msg)

def setup_logging() -> None:
    """Attach the in‑memory handler to the root logger.

    This should be called after ``logging.basicConfig`` so that the formatter is applied.
    """
    handler = InMemoryLogHandler()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)
