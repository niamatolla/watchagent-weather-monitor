import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from app.api.routes import router
from app.core.config import settings
from app.core.database import Base, engine
from app.models import reading, event
from app.services.poller import run_polling_loop

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    poller_task: asyncio.Task | None = None
    if settings.poller_enabled:
        poller_task = asyncio.create_task(
            run_polling_loop(settings.poll_interval_seconds)
        )

    try:
        yield
    finally:
        if poller_task is not None:
            poller_task.cancel()
            with suppress(asyncio.CancelledError):
                await poller_task


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)
