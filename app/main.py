from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.background import start_video_status_poller
from app.database import DATA_DIR, init_db
from app.routers import admin, characters, generations, products

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI UGC Generator")

init_db()
start_video_status_poller()

app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(generations.router, prefix="/api/generations", tags=["generations"])
app.include_router(admin.router, tags=["admin"])

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """This is a locally-run single-user dev tool that gets edited and pulled
    often — a stale cached copy of index.html/scripts.js/style.css silently
    showing old behavior after a `git pull` has been a recurring source of
    confusion. Since it's localhost, not a real client-facing site behind a
    CDN, the perf cost of never caching is irrelevant; always forcing a fresh
    fetch removes the whole "did I actually pull the latest?" question."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")
