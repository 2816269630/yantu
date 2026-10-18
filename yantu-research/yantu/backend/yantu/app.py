"""Application composition. Domain endpoints live in modules/<domain>/router.py."""

from contextlib import asynccontextmanager
from pathlib import Path
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from .core.dependencies import ServiceContext
from .core.errors import register_errors
from .integrations.plane import PlaneClient
from .integrations.ollama import OllamaResearchAssistant
from .migrations import migrate
from .modules.assistant.router import router as assistant_router
from .modules.auth.router import router as auth_router
from .modules.dashboard.router import router as dashboard_router
from .modules.drive.router import router as drive_router
from .modules.handovers.router import router as handovers_router
from .modules.learning.router import router as learning_router
from .modules.meetings.router import router as meetings_router
from .modules.notifications.router import router as notifications_router
from .modules.progress.router import router as progress_router
from .modules.tasks.router import router as tasks_router
from .modules.teams.router import router as teams_router


def create_app(
    database_url=None, upload_dir=None, frontend_dir=None, plane=None, research_assistant=None
) -> FastAPI:
    database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./yantu.db")
    uploads = Path(upload_dir or os.getenv("UPLOAD_DIR", "./uploads")).resolve()
    front = Path(frontend_dir or Path(__file__).resolve().parents[2] / "frontend")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=(
            {"check_same_thread": False, "timeout": 30} if database_url.startswith("sqlite") else {}
        ),
    )
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def sqlite_options(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")

    @asynccontextmanager
    async def lifespan(_app):
        uploads.mkdir(parents=True, exist_ok=True)
        migrate(engine)
        yield
        engine.dispose()

    app = FastAPI(title="研途 API", lifespan=lifespan)
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.services = ServiceContext(
        plane or PlaneClient(os.getenv("PLANE_BASE_URL", ""), os.getenv("PLANE_API_KEY", "")),
        uploads,
        research_assistant
        or OllamaResearchAssistant(os.getenv("AI_BASE_URL", ""), os.getenv("AI_MODEL", "")),
    )
    app.state.plane = app.state.services.plane
    register_errors(app)
    for router in (
        assistant_router,
        auth_router,
        dashboard_router,
        drive_router,
        handovers_router,
        learning_router,
        meetings_router,
        notifications_router,
        progress_router,
        tasks_router,
        teams_router,
    ):
        app.include_router(router)
    if front.is_dir():
        app.mount("/", StaticFiles(directory=front, html=True), name="frontend")
    return app


app = create_app()
