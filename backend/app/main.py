from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models  # noqa: F401 - registers tables on Base before create_all
from app.config import get_settings
from app.db import Base, engine, get_db
from app.logging_config import configure_logging
from app.routes.cases import router as cases_router

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent: only creates tables that don't already exist, never alters
    # or drops existing ones. Lets `docker compose up` work standalone.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Multi-Agent Task Resolution", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(cases_router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    checks = {"database": False, "bedrock_configured": False}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    try:
        get_settings()
        checks["bedrock_configured"] = True
    except Exception:
        pass

    status = "ok" if all(checks.values()) else "degraded"
    return {"status": status, "service": "multi-agent-task-resolution", "checks": checks}
