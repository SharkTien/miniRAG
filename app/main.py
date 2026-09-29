from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.database import DatabaseManager
from app.config.storage import StorageManager
from app.api.routers import documents, query, conversations

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    """Run the lifespan operation."""
    DatabaseManager().init_db()
    StorageManager().init_storage()
    yield
    # Shutdown

app = FastAPI(title="Mini RAG Pipeline", lifespan=lifespan)


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Provide the nocachemiddleware application component."""
    async def dispatch(self, request, call_next):
        """Apply the response middleware policy."""
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)

# Include Routers
app.include_router(documents.router, prefix="/api/documents")
# Keep the short paths required by the Mini RAG specification while retaining
# the existing /api namespace as a compatibility alias.
app.include_router(documents.router, prefix="/documents", include_in_schema=False)
app.include_router(query.router)
app.include_router(query.router, prefix="/api")
app.include_router(conversations.router)

@app.get("/health")
def health():
    """Return the service health status."""
    return {"status": "ok"}

@app.get("/")
def index():
    """Return backend service metadata and documentation links."""
    return {
        "service": "mini-rag",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }

@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    """Run the unexpected error operation."""
    print(f"Unhandled application error: {exc}")
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "internal_error",
                "message_key": "errors.internal_error",
            }
        },
    )
