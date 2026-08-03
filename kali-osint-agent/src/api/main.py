"""FastAPI application factory and server configuration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from configs.settings import settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialise databases on startup, clean up on
    shutdown."""
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("app.startup", environment=settings.environment.value)

    # Initialize PostgreSQL tables
    from src.db.postgres import init_db

    await init_db()
    logger.info("app.postgres_initialized")

    # Create Neo4j constraints
    from src.db.neo4j_client import neo4j_client

    try:
        await neo4j_client.init_constraints()
        logger.info("app.neo4j_constraints_created")
    except Exception as exc:
        logger.warning("app.neo4j_init_failed", error=str(exc))

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    from src.db.neo4j_client import neo4j_client as nc

    await nc.close()
    logger.info("app.shutdown_complete")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build and configure the FastAPI application with all routers,
    WebSocket endpoints, health checks, and login."""
    app = FastAPI(
        title="Kali OSINT Agent",
        description="LangGraph-powered OSINT agent dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Include API routers under /api prefix ────────────────────────────
    from src.api.routers.approvals import router as approvals_router
    from src.api.routers.cctv import router as cctv_router
    from src.api.routers.opsec import router as opsec_router
    from src.api.routers.reports import router as reports_router
    from src.api.routers.scope import router as scope_router
    from src.api.routers.tasks import router as tasks_router

    app.include_router(tasks_router, prefix="/api")
    app.include_router(approvals_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(scope_router, prefix="/api")
    app.include_router(cctv_router, prefix="/api")
    app.include_router(opsec_router, prefix="/api")

    # ── WebSocket ────────────────────────────────────────────────────────
    from src.api.websocket import websocket_endpoint

    app.add_api_websocket_route("/ws/tasks", websocket_endpoint)

    # ── Health endpoint ──────────────────────────────────────────────────

    class HealthResponse(BaseModel):
        status: str
        version: str

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check():
        return HealthResponse(status="ok", version="0.1.0")

    # ── Login endpoint ───────────────────────────────────────────────────

    class LoginRequest(BaseModel):
        username: str
        password: str

    class LoginResponse(BaseModel):
        access_token: str
        token_type: str = "bearer"

    @app.post("/api/auth/login", response_model=LoginResponse, tags=["auth"])
    async def login(request: LoginRequest):
        from fastapi import HTTPException

        from src.api.auth import USERS_DB, create_access_token, verify_password

        user = USERS_DB.get(request.username)
        if not user or not verify_password(request.password, user["hashed_password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_access_token({"sub": request.username, "role": user["role"]})
        return LoginResponse(access_token=token)

    return app


# Module-level application instance
app = create_app()
