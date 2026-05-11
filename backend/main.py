from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
import socketio
import os
import logging

from database import SessionLocal, engine, Base, get_db
from auth import router as auth_router
from workflows import router as workflows_router
from components import router as components_router
from executions import router as executions_router
from webhooks import router as webhooks_router
from variables import router as variables_router
from api_keys import router as api_keys_router
from fireflies import router as fireflies_router
from email_queue import router as email_queue_router
from sms import router as sms_router
from email_sequences import router as email_sequences_router
from contacts import router as contacts_router
from contact_orgs import router as contact_orgs_router
from gmail_proxy import router as gmail_proxy_router
from outlook_proxy import router as outlook_proxy_router
from admin import router as admin_router
from system_config import router as system_config_router
from paddle_webhooks import router as paddle_router
from team import router as team_router
from demo_transcripts import router as demo_transcripts_router
from resources import router as resources_router
from websocket_manager import WebSocketManager
from config import get_deployment_mode
from logging_config import setup_logging
from middleware import RequestLoggingMiddleware, PerformanceMonitorMiddleware
import models

# Initialize logging system
log_level = os.getenv("LOG_LEVEL", "INFO")
setup_logging(log_level)
logger = logging.getLogger(__name__)

# Database initialization is now handled by Alembic migrations
# Tables will be created/updated via migrate.py before app starts

# Determine if we're in production mode
is_production = get_deployment_mode() == "production"

# Initialize FastAPI app
# Disable API documentation in production for security
app = FastAPI(
    title="Workflow Automation Platform",
    description="A comprehensive platform for call transcript processing and CRM integration",
    version="1.0.0",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json"
)

# Add request logging and performance monitoring middleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(PerformanceMonitorMiddleware, slow_threshold_ms=3000)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "https://aibot2.integratedpipedrive.com"  # Production domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("FastAPI application initialized with logging and monitoring middleware")

# Security
security = HTTPBearer()

# Initialize WebSocket manager
websocket_manager = WebSocketManager()

# Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins="*"
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(workflows_router, prefix="/workflows", tags=["Workflows"])
app.include_router(components_router, prefix="/components", tags=["Components"])
app.include_router(executions_router, prefix="/executions", tags=["Executions"])
app.include_router(webhooks_router, prefix="", tags=["Webhooks"])
app.include_router(variables_router, prefix="", tags=["Variables"])
app.include_router(api_keys_router, prefix="", tags=["API Keys"])
app.include_router(fireflies_router, prefix="", tags=["Fireflies"])
app.include_router(email_queue_router, prefix="/emails", tags=["Email Queue"])
app.include_router(sms_router, prefix="/sms", tags=["SMS"])
app.include_router(email_sequences_router, prefix="/email-sequences", tags=["Email Sequences"])
app.include_router(contacts_router, prefix="/contacts", tags=["Contacts"])
app.include_router(contact_orgs_router, prefix="/contact-organizations", tags=["Contact Organizations"])
app.include_router(gmail_proxy_router, prefix="/gmail", tags=["Gmail"])
app.include_router(outlook_proxy_router, prefix="/outlook", tags=["Outlook"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(system_config_router, prefix="/system-config", tags=["System Config"])
app.include_router(paddle_router, prefix="", tags=["Billing"])
app.include_router(team_router, prefix="/team", tags=["Team"])
app.include_router(demo_transcripts_router, prefix="", tags=["Demo Transcripts"])
app.include_router(resources_router, tags=["Resources"])

def _validate_startup_models() -> None:
    """Run rag_service.validate_configured_models with the right exception
    triage:

      - ConfiguredModelError → fatal. A bad model id will silently break AI
        Filters and email generation, so we want startup to crash loud.
      - Anything else (OperationalError on a DB blip, ImportError on a partial
        install, network hiccup) → log and proceed. Issue #140: a momentary
        Postgres unavailability during a rolling deploy or docker-compose boot
        race used to take the whole API down. Validation will re-run on the
        next restart; meanwhile the service should stay up so health checks
        and dependency-free routes continue to serve.
    """
    try:
        from rag_service import validate_configured_models, ConfiguredModelError
    except Exception:
        logger.exception("could not import rag_service for startup validation; skipping")
        return

    try:
        validate_configured_models()
    except ConfiguredModelError:
        logger.exception("RAG model configuration is invalid — aborting startup")
        raise
    except Exception:
        logger.exception("startup model validation skipped (transient/non-fatal)")


@app.on_event("startup")
async def startup_event():
    """Log application startup and validate critical SystemConfig."""
    logger.info("=" * 80)
    logger.info("Workflow Automation Platform API starting up")
    logger.info(f"Deployment mode: {get_deployment_mode()}")
    logger.info(f"Log level: {log_level}")
    logger.info(f"Documentation: {'disabled' if is_production else 'enabled at /docs'}")
    logger.info("=" * 80)

    _validate_startup_models()


@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown."""
    logger.info("Workflow Automation Platform API shutting down")


@app.get(
    "/",
    summary="API Root",
    description="Returns basic information about the Workflow Automation Platform API",
    tags=["System"],
    response_description="Welcome message with API name"
)
async def root():
    """
    Get API root information.

    Returns a welcome message identifying this as the Workflow Automation Platform API.
    This endpoint can be used to verify that the API is accessible.
    """
    return {"message": "Workflow Automation Platform API"}

@app.get(
    "/health",
    summary="Health Check",
    description="Check the health status of the API server",
    tags=["System"],
    response_description="Health status of the API"
)
async def health_check():
    """
    Perform a health check on the API.

    This endpoint is useful for monitoring and load balancers to verify
    that the API server is running and responsive.

    Returns:
        dict: A dictionary with the current health status
    """
    return {"status": "healthy"}

# Socket.IO events
@sio.event
async def connect(sid, environ):
    print(f"Client {sid} connected")
    await websocket_manager.connect(sid)

@sio.event
async def disconnect(sid):
    print(f"Client {sid} disconnected")
    await websocket_manager.disconnect(sid)

@sio.event
async def join_workflow(sid, data):
    workflow_id = data.get('workflow_id')
    if workflow_id:
        await websocket_manager.join_workflow(sid, workflow_id)

# Mount Socket.IO
socket_app = socketio.ASGIApp(sio, app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:socket_app", host="0.0.0.0", port=9000, reload=True)