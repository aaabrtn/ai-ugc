# AI UGC Generator (KLIQMGMT)

Local web app for generating SOP-validated AI UGC fashion try-on videos: character profiles → product URL → validated prompt → KIE video generation → Google Drive save.

Built in phases per `AIUGC_CLAUDE_CODE_PROJECT_SPEC.md`. See **Status** below for what's live.

## Status

- [x] **Phase 1 — Character Manager**: create, view, edit, delete characters. Setting is locked once first saved; editing it requires an explicit confirmation.
- [ ] Phase 2 — Product URL → SOP-validated prompt generation
- [ ] Phase 3 — KIE API video generation
- [ ] Phase 4 — Google Drive save
- [ ] Phase 5 — Job history

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000

Data (SQLite DB + uploaded images) is stored under `data/`, which is gitignored — it's local, runtime state, not source.

## Project layout

```
app/
  main.py              FastAPI app, static/upload mounts
  database.py           SQLite engine/session setup
  models.py              SQLAlchemy models (Character, CharacterImage)
  schemas.py              Pydantic response models
  routers/characters.py    Character CRUD API
static/                    Frontend (plain HTML/CSS/JS, no build step)
docs/AI-UGC-Content-SOP.md  SOP the app reads from (Phase 2) — edit this file to update the rules the app validates prompts against; no code change needed
data/                       SQLite DB + uploaded images (gitignored, created at runtime)
```

## Notes on the Character model

- `consent_status`: `cleared` or `internal_only`. From Phase 3 onward, `internal_only` characters can still generate prompts for review, but the "Generate Video" button is disabled with a warning.
- `setting` (description + reference images) is **locked as soon as a character is first saved**. Editing it later requires an explicit confirm step in the UI, since it changes the look of every future video with that character.
- `movement_notes` is optional — blank means the app uses the SOP's default 5-cut movement pattern (Phase 2+).

## What's needed from Andrew before later phases

Not required for Phase 1, but flagging now so they're ready when we get there:

- **Phase 3 (KIE API)**: a KIE API key/credentials, and confirmation of the exact endpoint(s)/response shape (job submission + polling) to integrate against.
- **Phase 4 (Google Drive)**: Google OAuth credentials (or a service account) with Drive write access, and which Drive/folder root the dated folders should be created under.
- **Phase 2 (product scraping)**: confirmation on TikTok Shop URL handling in particular — TikTok Shop pages are often JS-rendered/bot-protected, which may need a headless-browser fetch rather than a plain HTTP request. Will surface clearly in the UI if a given URL can't be scraped cleanly rather than guessing.
