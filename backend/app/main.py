from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.graph_service import graph_service
from app.controllers import admin_controller, auth_controller, chat_controller
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.base import Base
from app.db.session import engine
from app.exceptions import AppError
import app.models  # noqa: F401  ensures all ORM models are registered on Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    Base.metadata.create_all(bind=engine)
    graph_service.setup()
    yield
    graph_service.close()


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


app.include_router(auth_controller.router, prefix=settings.API_V1_PREFIX)
app.include_router(chat_controller.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_controller.router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.APP_NAME}
