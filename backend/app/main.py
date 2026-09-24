from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.db import SessionLocal, get_db
from app.services.auth.bootstrap import bootstrap_admin


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.algo_version)

    @app.on_event("startup")
    def initialize_admin() -> None:
        with SessionLocal() as db:
            bootstrap_admin(db)

    @app.get("/health")
    def health(db: Session = Depends(get_db)) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"status": "unavailable", "database": "unavailable"},
            ) from exc
        return {"status": "ok", "app": settings.app_name, "database": "ok"}

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
