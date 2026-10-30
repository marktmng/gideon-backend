"""Main FastAPI application entrypoint for Gideon AI Assistant."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.exceptions import (
    EntityNotFoundError,
    GideonException,
    AIProviderError,
    AIConfigurationError,
    AIRateLimitError,
    AIProviderTimeoutError,
)
from app.core.logging import setup_logging, get_logger
from app.db.session import verify_database_connection, engine, SessionLocal
from app.db.base import Base

# Initialize logging
setup_logging(debug=settings.debug)
logger = get_logger(__name__)


def reconcile_orphaned_agent_tasks(db=None):
    """Reconcile tasks left in running or planning states due to unexpected backend termination."""
    from app.models.agent import AgentTask
    from app.schemas.agent import TaskStatusEnum, StepStatusEnum

    def _reconcile(session):
        interrupted_tasks = session.query(AgentTask).filter(
            AgentTask.status.in_([TaskStatusEnum.running.value, TaskStatusEnum.planning.value])
        ).all()
        for task in interrupted_tasks:
            task.status = TaskStatusEnum.failed.value
            task.error_message = "Task execution interrupted by backend server restart."
            task.completed_at = datetime.now(timezone.utc)
            for step in (task.steps or []):
                if step.status == StepStatusEnum.running.value:
                    step.status = StepStatusEnum.failed.value
                    step.error_message = "Step execution interrupted by backend server restart."
                    step.completed_at = datetime.now(timezone.utc)
        if interrupted_tasks:
            session.commit()
            logger.info("Reconciled %d orphaned task(s) from previous server session.", len(interrupted_tasks))

    try:
        if db is not None:
            _reconcile(db)
        else:
            with SessionLocal() as session:
                _reconcile(session)
    except Exception as e:
        logger.warning("Could not reconcile orphaned tasks: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s in %s mode...", settings.app_name, settings.app_env)
    # Verify database connection
    try:
        verify_database_connection()
        # In SQLite development mode, ensure tables exist if migrations have not yet been run
        if settings.is_sqlite:
            Base.metadata.create_all(bind=engine)
            logger.info("SQLite schema verified.")
        reconcile_orphaned_agent_tasks()
    except Exception as e:
        logger.error("Startup database check encountered an issue: %s", str(e))
    yield
    logger.info("Shutting down %s...", settings.app_name)


app = FastAPI(
    title="Gideon AI Assistant API",
    description="Backend service for Gideon AI Assistant — Phase 1: Core Architecture, Conversations, Tasks, and Extensible AI Provider.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS configuration - permissive for local desktop assistant frontend and tools
origins = [
    settings.frontend_origin,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error_type": "EntityNotFound"}
    )


@app.exception_handler(AIConfigurationError)
async def ai_configuration_error_handler(request: Request, exc: AIConfigurationError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "error_type": "AIConfigurationError"}
    )


@app.exception_handler(AIRateLimitError)
async def ai_rate_limit_error_handler(request: Request, exc: AIRateLimitError):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": str(exc), "error_type": "AIRateLimitError"}
    )


@app.exception_handler(AIProviderTimeoutError)
async def ai_timeout_error_handler(request: Request, exc: AIProviderTimeoutError):
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={"detail": str(exc), "error_type": "AIProviderTimeoutError"}
    )


@app.exception_handler(AIProviderError)
async def ai_provider_error_handler(request: Request, exc: AIProviderError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc), "error_type": "AIProviderError"}
    )


@app.exception_handler(GideonException)
async def gideon_exception_handler(request: Request, exc: GideonException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "error_type": "GideonDomainError"}
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error processing request %s %s: %s", request.method, request.url.path, str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred.", "error_type": "InternalServerError"}
    )


# Root health endpoint
app.include_router(health_router)

# Versioned API routes
app.include_router(api_router, prefix=settings.api_v1_prefix)
