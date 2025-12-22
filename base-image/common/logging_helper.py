"""
Structured logging utilities for FAVE functions.

All logs are emitted as JSON lines to stdout so OpenFaaS/Loki can ingest them easily.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from typing import Any, Dict, Optional

HOSTNAME = socket.gethostname()
SERVICE_NAME = os.getenv("FUNCTION_NAME", "unknown-function")


def log_event(stage: str, event: str, request_id: Optional[str] = None, **fields: Any) -> None:
    """
    Emit a structured log line.

    Example:
        log_event("stage-ffmpeg-0", "start", request_id="abc", input_uri="s3://...")
    """
    record: Dict[str, Any] = {
        "timestamp": time.time(),
        "stage": stage,
        "event": event,
        "request_id": request_id,
        "service": SERVICE_NAME,
        "host": HOSTNAME,
    }
    record.update(fields)
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()


def log_exception(stage: str, request_id: Optional[str], exc: Exception) -> None:
    """Convenience helper to log exceptions with stack trace string."""
    log_event(stage, "error", request_id=request_id, error_type=type(exc).__name__, error=str(exc))
