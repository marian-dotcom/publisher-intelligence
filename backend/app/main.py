from fastapi import FastAPI

from app.api.health import router as health_router
from app.common.logging import configure_logging
from app.config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title="Publisher Incident Intelligence",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    application.include_router(health_router)
    return application


app = create_app()
