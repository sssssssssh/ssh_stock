from fastapi import APIRouter, Depends

from app.api.v1 import (
    auth,
    dashboard,
    jobs,
    opportunities,
    research,
    sectors,
    stocks,
    system,
    themes,
)
from app.services.auth.dependencies import require_authenticated_user

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
protected = APIRouter(dependencies=[Depends(require_authenticated_user)])
protected.include_router(system.router, prefix="/system", tags=["system"])
protected.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
protected.include_router(sectors.router, prefix="/sectors", tags=["sectors"])
protected.include_router(themes.router, prefix="/themes", tags=["themes"])
protected.include_router(opportunities.router, prefix="/opportunities", tags=["opportunities"])
protected.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
protected.include_router(research.router, prefix="/research", tags=["research"])
protected.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(protected)
