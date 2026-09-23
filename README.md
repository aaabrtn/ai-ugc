# AI UGC Generator (KLIQMGMT)

Local web app for generating SOP-validated AI UGC fashion try-on videos: character profiles → product URL → validated prompt → KIE video generation → Google Drive save.

Built in phases per `AIUGC_CLAUDE_CODE_PROJECT_SPEC.md`. See **Status** below for what's live.

## Status

- [x] **Phase 1 — Character Manager**: create, view, edit, delete characters. Setting is locked once first saved; editing it requires an explicit confirmation.
- [~] **Phase 2 — Product fetch (in progress)**: give a character a product URL (or manual photos) and it fetches product images. SOP-validated prompt generation is not built yet — see below.
- [ ] Phase 3 — KIE API video generation
- [ ] Phase 4 — Google Drive save
- [ ] Phase 5 — Job history

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

`playwright install chromium` downloads the headless browser used as the last-resort product-fetch method (see below) — only needed once.

## Run

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000

Data (SQLite DB + uploaded images) is stored under `data/`, which is gitignored — it's local, runtime state, not source.

## Project layout

```
app/
  main.py                 FastAPI app, static/upload mounts
  database.py              SQLite engine/session setup
  models.py                 SQLAlchemy models (Character, CharacterImage, Job, JobImage)
  schemas.py                 Pydantic response models
  routers/characters.py       Character CRUD API
  routers/jobs.py              Product job API (fetch product photos for a character)
  scraping/methods.py           The three product-fetch methods (see below)
  scraping/fetch.py              Orchestrates the fallback chain across those methods
  scraping/download.py            Downloads found image URLs to local storage
static/                    Frontend (plain HTML/CSS/JS, no build step)
docs/AI-UGC-Content-SOP.md  SOP the app reads from (Phase 2) — edit this file to update the rules the app validates prompts against; no code change needed
data/                       SQLite DB + uploaded images (gitignored, created at runtime)
```

## How product fetching works (Phase 2)

On the **Products** tab, pick a character, give it a product URL (their website, a TikTok Shop link, a Kalodata link, etc.), and optionally attach product photos manually as a fail-safe.

The URL is always tried first, through three methods in order, cheapest/most reliable first:

1. **Structured data** — one plain HTTP request, reading the page's `schema.org` Product JSON-LD and Open Graph tags. Fast, works on most modern storefronts without running any JavaScript.
2. **HTML scrape** — a broader plain HTTP request that scans every `<img>` tag in the raw page HTML. Catches simpler sites that don't publish structured product data.
3. **Headless browser** — actually renders the page in Chromium (via Playwright) and re-scans it. This is the one that can handle JS-heavy storefronts (TikTok Shop and similar) that return near-empty HTML to a plain request.

The first method that finds usable images wins. If all three fail:

- If manual photos were attached to the same submission, those are used instead, and the product page shows a note explaining the URL fetch failed and manual photos were used.
- If no manual photos were provided, the job is saved as **Failed**, with a plain-English explanation of what was tried and why each method didn't work — never a silent failure or a prompt built from partial data.

What's **not** built yet: turning the fetched product photos + character + SOP into an actual validated video prompt. That's the next piece of Phase 2, and depends on how garment descriptions get written (scraped text vs. an AI vision pass over the product photos) — flagged below.

## Notes on the Character model

A character has exactly four inputs: **name**, **characteristics** (free text), **character reference photos**, and **settings reference photos**. Physical traits (face, hair, skin tone, build, etc.) are read directly from the reference photos rather than entered as structured fields — `characteristics` is just additional context on top of that.

- `setting` (reference photos of the filming location) is **locked as soon as a character is first saved**. Editing it later requires an explicit confirm step in the UI, since it changes the look of every future video with that character.

## What's needed from Andrew before later phases

- **Phase 2 (prompt generation, next up)**: how should garment descriptions get written? The SOP demands precise, product-accurate garment detail (colour, material, hardware, trims). Scraped page text is often too thin for that — the more reliable option is an AI vision pass over the fetched product photos to write the description, which needs an API key (e.g. Anthropic) the app can call. Worth confirming before this gets built.
- **Phase 3 (KIE API)**: a KIE API key/credentials, and confirmation of the exact endpoint(s)/response shape (job submission + polling) to integrate against.
- **Phase 4 (Google Drive)**: Google OAuth credentials (or a service account) with Drive write access, and which Drive/folder root the dated folders should be created under.
- **Real-world testing of the product-fetch chain**: it's been tested against local mock pages (this sandbox can't reach the open internet), so it needs a pass against real TikTok Shop, Kalodata, and brand-website URLs to see which method each one actually needs, and to tune the image-filtering heuristics if needed.
