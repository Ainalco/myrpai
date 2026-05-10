"""
Centralized logging configuration with structured logging and request tracking.

PII-in-logs policy
------------------
Logs from this service are shipped to external aggregators (Datadog, CloudWatch,
etc.) with retention periods that may exceed the Postgres retention window for
the source data. Anything written to a log must respect the stricter retention
contract.

What counts as PII in this codebase:
  * Call transcript text, email bodies, CRM notes, and any chunk_text retrieved
    from content_embeddings.
  * Names, email addresses, phone numbers, and financial details extracted
    from the above.
  * Raw request/response bodies from third-party APIs (OpenAI, Anthropic,
    Fireflies, Pipedrive) — error responses in particular echo the submitted
    input on many failure modes.

Rules by log level:
  * INFO / WARNING / ERROR — MUST NOT contain PII. Log structural metadata
    only: ids, row counts, sizes, status codes, error codes/types, timing.
  * DEBUG — MAY contain short previews of PII, but only when:
      1. The preview is routed through a redaction helper that truncates
         to ~100 chars (see rag_service._redact); and
      2. The log site is gated on an explicit opt-in env flag
         (RAG_DEBUG_PII=true for rag_service). The default-off gate prevents
         a prod log-level flip from exposing PII to the aggregator.
  * Third-party error bodies — never log raw. Extract structured fields
    (code, type, message) and redact the message; see
    rag_service._sanitize_openai_error for the pattern.

When adding new log sites, assume logs flow to an external store with longer
retention than the underlying DB. If in doubt, log an id and look the content
up out-of-band.
"""
import logging
import sys
from datetime import datetime
from typing import Optional
import contextvars

# Context variable to store request ID across async calls
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('request_id', default=None)

class RequestIdFilter(logging.Filter):
    """Add request ID to log records."""

    def filter(self, record):
        record.request_id = request_id_var.get() or "no-request-id"
        return True

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }

    def format(self, record):
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"

        # Format the message
        result = super().format(record)

        # Reset levelname for next use
        record.levelname = levelname

        return result

def setup_logging(log_level: str = "INFO"):
    """
    Configure application-wide logging with structured format and request ID tracking.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """

    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create console handler with colored formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    # Detailed format with request ID, timestamp, level, logger name, and message
    log_format = (
        '%(asctime)s | %(levelname)-8s | %(request_id)s | '
        '%(name)s:%(funcName)s:%(lineno)d | %(message)s'
    )

    formatter = ColoredFormatter(
        fmt=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)

    # Add request ID filter
    request_id_filter = RequestIdFilter()
    console_handler.addFilter(request_id_filter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Add our console handler
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    logging.info("Logging system initialized with level: %s", log_level)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str):
    """Set the request ID in context for the current async task."""
    request_id_var.set(request_id)


def clear_request_id():
    """Clear the request ID from context."""
    request_id_var.set(None)
