from fastapi import APIRouter

from app.api.routes import (
    ai,
    assets,
    auth,
    dashboard,
    exports,
    jobs,
    models,
    operations,
    organisations,
    projects,
    providers,
    reports,
    roles,
    settings,
    storage,
    transcripts,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(assets.router)
api_router.include_router(jobs.router)
api_router.include_router(transcripts.router)
api_router.include_router(exports.router)
api_router.include_router(models.router)
api_router.include_router(organisations.router)
api_router.include_router(operations.router)
api_router.include_router(providers.router)
api_router.include_router(ai.router)
api_router.include_router(reports.router)
api_router.include_router(roles.router)
api_router.include_router(dashboard.router)
api_router.include_router(settings.router)
api_router.include_router(storage.router)
api_router.include_router(users.router)
