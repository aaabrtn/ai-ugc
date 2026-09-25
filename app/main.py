import base64
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request, Response
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


APP_USERNAME = os.environ.get("APP_USERNAME", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")


@app.middleware("http")
async def require_basic_auth(request: Request, call_next):
    """This app has no user-account system -- it was always a single-user
    tool only ever reachable on localhost. Once hosted at a public URL,
    anyone who finds that URL could otherwise generate videos on this
    account's Anthropic/KIE credits, or see product/character data. Gates
    every route (including static files and uploads) behind HTTP Basic Auth
    once APP_USERNAME/APP_PASSWORD are set; unset (the local-dev default),
    it's a no-op -- matches the pre-hosting behavior exactly."""
    if not APP_USERNAME or not APP_PASSWORD:
        return await call_next(request)

    username, password = "", ""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, _, password = decoded.partition(":")
        except (ValueError, UnicodeDecodeError):
            pass

    if secrets.compare_digest(username, APP_USERNAME) and secrets.compare_digest(password, APP_PASSWORD):
        return await call_next(request)

    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="AI UGC Generator"'})


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
