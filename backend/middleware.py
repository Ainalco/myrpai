"""
FastAPI middleware for request/response logging and monitoring.
"""
import logging
import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from logging_config import set_request_id, clear_request_id

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all HTTP requests and responses with timing and request ID tracking.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]  # Short UUID for readability

        # Store request ID in context for this async task
        set_request_id(request_id)

        # Add request ID to request state for access in route handlers
        request.state.request_id = request_id

        # Log incoming request
        start_time = time.time()

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Log request details
        logger.info(
            f"REQUEST | {request.method} {request.url.path} | "
            f"Client: {client_ip} | Query: {dict(request.query_params) if request.query_params else 'none'}"
        )

        # Process request and catch any errors
        response = None
        error_occurred = False
        error_message = None

        try:
            response = await call_next(request)
        except Exception as e:
            error_occurred = True
            error_message = str(e)
            logger.error(
                f"UNHANDLED ERROR | {request.method} {request.url.path} | Error: {error_message}",
                exc_info=True
            )
            # Return a 500 error response
            from fastapi.responses import JSONResponse
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": f"Internal server error: {error_message}",
                    "request_id": request_id
                }
            )

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log response with timing
        status_code = response.status_code
        log_level = logging.INFO

        # Use WARNING for slow requests (> 5 seconds) or 4xx errors
        if duration_ms > 5000:
            log_level = logging.WARNING
        elif 400 <= status_code < 500:
            log_level = logging.WARNING
        # Use ERROR for 5xx errors
        elif status_code >= 500:
            log_level = logging.ERROR

        logger.log(
            log_level,
            f"RESPONSE | {request.method} {request.url.path} | "
            f"Status: {status_code} | Duration: {duration_ms:.2f}ms"
        )

        # Log warning for slow requests
        if duration_ms > 5000:
            logger.warning(
                f"SLOW REQUEST | {request.method} {request.url.path} took {duration_ms:.2f}ms"
            )

        # Clear request ID from context
        clear_request_id()

        return response


class PerformanceMonitorMiddleware(BaseHTTPMiddleware):
    """
    Middleware to monitor endpoint performance and log statistics.
    """

    def __init__(self, app: ASGIApp, slow_threshold_ms: float = 3000):
        super().__init__(app)
        self.slow_threshold_ms = slow_threshold_ms

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Check if request exceeded threshold
        if duration_ms > self.slow_threshold_ms:
            logger.warning(
                f"PERFORMANCE | Endpoint {request.method} {request.url.path} "
                f"exceeded threshold: {duration_ms:.2f}ms (threshold: {self.slow_threshold_ms}ms)"
            )

        return response
