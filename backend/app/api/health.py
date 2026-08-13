from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from app.config.settings import get_settings
from app.db.session import get_engine
from app.storage.s3 import S3Storage

router = APIRouter(prefix="/health", tags=["health"])


async def database_ready() -> bool:
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def object_storage_ready() -> bool:
    try:
        storage = S3Storage(get_settings())
        return await run_in_threadpool(storage.bucket_exists)
    except Exception:
        return False


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    database: Annotated[bool, Depends(database_ready)],
    object_storage: Annotated[bool, Depends(object_storage_ready)],
) -> dict[str, object]:
    dependencies = {"database": database, "object_storage": object_storage}
    if not all(dependencies.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependencies": dependencies},
        )
    return {"status": "ready", "dependencies": dependencies}
