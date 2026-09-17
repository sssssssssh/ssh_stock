from fastapi import APIRouter

from app.api.v1 import dashboard, jobs, opportunities, research, sectors, stocks, system, themes

api_router = APIRouter()
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(sectors.router, prefix="/sectors", tags=["sectors"])
api_router.include_router(themes.router, prefix="/themes", tags=["themes"])
api_router.include_router(opportunities.router, prefix="/opportunities", tags=["opportunities"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
api_router.include_router(research.router, prefix="/research", tags=["research"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
