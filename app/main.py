from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import DatabaseManager
from app.core.storage import StorageManager
from app.api.routers import auth, documents, query, conversations

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    DatabaseManager().init_db()
    StorageManager().init_storage()
    yield
    # Shutdown

app = FastAPI(title="Mini RAG Pipeline", lifespan=lifespan)


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)

# Setup Templates & Static
import os
os.makedirs("frontend/dist/assets", exist_ok=True)
templates = Jinja2Templates(directory="frontend/dist")
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

@app.get("/pdf.worker.min.mjs")
def get_pdf_worker():
    for p in ["frontend/dist/pdf.worker.min.mjs", "frontend/public/pdf.worker.min.mjs"]:
        if os.path.exists(p):
            from fastapi.responses import FileResponse
            return FileResponse(p, media_type="application/javascript")
    from fastapi import HTTPException
    raise HTTPException(404, "Worker not found")

# Include Routers
app.include_router(auth.router)
app.include_router(documents.router, prefix="/api/documents")
# Keep the short paths required by the Mini RAG specification while retaining
# the existing /api namespace used by the frontend.
app.include_router(documents.router, prefix="/documents", include_in_schema=False)
app.include_router(query.router)
app.include_router(query.router, prefix="/api")
app.include_router(conversations.router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi.responses import Response
    return Response(content=b"", media_type="image/x-icon", status_code=204)

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    print(f"Lỗi hệ thống: {str(exc)}")
    return JSONResponse(status_code=503, content={"detail": "Dịch vụ gặp lỗi nội bộ."})
