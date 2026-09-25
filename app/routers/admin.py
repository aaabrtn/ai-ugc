"""TEMPORARY migration helper -- lets an existing local data/ folder (SQLite
db + uploaded images/videos) be copied onto a freshly hosted deploy's
persistent volume, since the two started as separate, unconnected databases.
Delete this router (and its include_router() call in main.py) once the
one-time migration it's used for is done -- it's a live file-write endpoint
and has no reason to stay in a shipped app."""

import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, UploadFile

from app.database import DATA_DIR, engine

router = APIRouter()

ADMIN_IMPORT_TOKEN = os.environ.get("ADMIN_IMPORT_TOKEN", "")


@router.post("/admin/import-data")
async def import_data(file: UploadFile, x_admin_token: str = Header(default="")):
    # 404, not 403 -- an unset token means this deploy never opted in, and a
    # wrong token shouldn't reveal that the route exists at all.
    if not ADMIN_IMPORT_TOKEN or x_admin_token != ADMIN_IMPORT_TOKEN:
        raise HTTPException(status_code=404)

    # Drop pooled connections to the current (soon to be replaced) db file
    # before touching it on disk.
    engine.dispose()

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "import.zip"
        with open(zip_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        extract_dir = (Path(tmp) / "extracted").resolve()
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                member_path = (extract_dir / member).resolve()
                if extract_dir != member_path and extract_dir not in member_path.parents:
                    raise HTTPException(status_code=400, detail=f"Unsafe path in zip: {member}")
            zf.extractall(extract_dir)

        # Accept a zip of the data/ folder's contents, or of the data/ folder
        # itself (a single top-level directory) -- so the exact zip command
        # used doesn't have to be exact.
        source = extract_dir
        contents = list(extract_dir.iterdir())
        if len(contents) == 1 and contents[0].is_dir():
            source = contents[0]

        for item in source.iterdir():
            dest = DATA_DIR / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

    return {
        "status": "ok",
        "detail": "Data imported. Restart the service so the app opens the new database cleanly.",
    }
