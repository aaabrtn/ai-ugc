from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import DATA_DIR, init_db
from app.routers import characters, generations, products

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI UGC Generator")

init_db()

app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(generations.router, prefix="/api/generations", tags=["generations"])

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")
