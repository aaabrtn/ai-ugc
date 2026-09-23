# AI UGC Generator (KLIQMGMT)

Local web app for generating SOP-validated AI UGC fashion try-on videos: character catalogue + product catalogue → a script pairing the two → validated prompt → KIE video generation → Google Drive save.

Built in phases per `AIUGC_CLAUDE_CODE_PROJECT_SPEC.md`. See **Status** below for what's live.

## Status

- [x] **Phase 1 — Character Manager**: create, view, edit, delete characters. Setting is locked once first saved; editing it requires an explicit confirmation.
- [x] **Phase 2 — Product catalogue → SOP-validated prompt**: add products to a reusable catalogue (URL fetch or manual photos), then pair a character with a product on the Generator (the app's home screen) to generate a full SOP-compliant video prompt from AI-vision-read character/setting/garment photos, with automated SOP checks and an editable review/approve step. See below for all three halves.
- [x] **Phase 3 — KIE video generation**: once a script's prompt is approved, **Generate Video** submits it to KIE (`gemini-omni-video`) using the character's KIE character ID plus its setting/garment reference photos, and polls automatically until it's done — see below. Needs `KIE_API_KEY` (no other setup required — see below).
- [ ] Phase 4 — Google Drive save of the *finished video* to a dated folder (not yet built).
- [x] **Phase 5 — Script history**: the Generator's list view is the job history — character, product, stage, video status, and date on every card. Click a card to re-open its prompt.

## The app's shape: two catalogues + a Generator

- **Characters** and **Products** are catalogues — reusable, independent of each other. A tab each, reached from the nav pills at the top.
- **The Generator is the app's home screen** (no tab of its own — click the logo to get back to it from anywhere). This is where you pick a character and a product from the two catalogues, generate a script's prompt, review and approve it, and generate the video.

Products and prompt generation used to be bundled into one combined flow; they're deliberately separate now. A product's photos and a character's identity are independent concerns that only come together when you're actually generating a specific script — so fetch a product once, and generate as many scripts against it as you like, with any character, without re-fetching.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # then fill in the keys below
```

- `playwright install chromium` downloads the headless browser used as the last-resort product-fetch method (see below) — only needed once.
- `ANTHROPIC_API_KEY` is required for prompt generation (see **How prompt generation works** below).
- `KIE_API_KEY` is required for video generation (see **How video generation works** below) — nothing else to set up for it.

Each is independent — without either of them, the parts that don't need it still work fine, and the app tells you clearly what's missing rather than failing silently.

## Run

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000

Data (SQLite DB + uploaded images) is stored under `data/`, which is gitignored — it's local, runtime state, not source.

## Project layout

```
app/
  main.py                    FastAPI app, static/upload mounts
  config.py                   Reads ANTHROPIC_API_KEY, KIE_API_KEY from environment / .env
  database.py                  SQLite engine/session setup
  models.py                     SQLAlchemy models (Character, CharacterImage, Product, ProductImage, Generation)
  schemas.py                     Pydantic response models
  routers/characters.py           Character CRUD API + KIE character registration
  routers/products.py              Product catalogue API: fetch/create, edit name/context, add/remove photos
  routers/generations.py            Script API: create (character+product), generate/approve prompt, submit/poll video
  scraping/methods.py               The three product-fetch methods (see below)
  scraping/fetch.py                  Orchestrates the fallback chain across those methods
  scraping/download.py                Downloads found image URLs to local storage
  generation/vision.py                 AI vision analysis of garment/persona/setting photos
  generation/template.py                Deterministic SOP-compliant prompt assembly
  generation/sop_check.py                Automated SOP Pre-Send Checklist checks
  integrations/kie.py                   KIE client: register a character, submit a video task, poll its status
  integrations/catbox.py                Anonymous public image hosting for KIE's input images (no setup)
static/                    Frontend (plain HTML/CSS/JS, no build step) — app.js (characters),
                             products.js, scripts.js (the Generator) — all three share globals as
                             classic scripts
docs/AI-UGC-Content-SOP.md  SOP the app reads from — edit this file to update the rules
                             prompts are checked against; the checks themselves live in
                             generation/sop_check.py and need updating too if the SOP's
                             mechanically-checkable rules change
data/                       SQLite DB + uploaded images (gitignored, created at runtime)
```

## How the product catalogue works

On the **Products** tab, **+ New Product** gives it a URL (their website, a TikTok Shop link, a Kalodata link, etc.), and optionally attach photos manually as a fail-safe.

The URL is always tried first, through three methods in order, cheapest/most reliable first:

1. **Structured data** — one plain HTTP request, reading the page's `schema.org` Product JSON-LD and Open Graph tags. Fast, works on most modern storefronts without running any JavaScript.
2. **HTML scrape** — a broader plain HTTP request that scans every `<img>` tag in the raw page HTML. Catches simpler sites that don't publish structured product data.
3. **Headless browser** — actually renders the page in Chromium (via Playwright) and re-scans it. This is the one that can handle JS-heavy storefronts (TikTok Shop and similar) that return near-empty HTML to a plain request.

The first method that finds usable images wins. If all three fail:

- If manual photos were attached to the same submission, those are used instead, and the product page shows a note explaining the URL fetch failed and manual photos were used.
- If no manual photos were provided, the product is saved as **Failed**, with a plain-English explanation of what was tried and why each method didn't work — never a silent failure or a prompt built from partial data.

Once a product exists, its detail page lets you:
- **Rename it** to something short and memorable (defaults to the scraped page title).
- **Add or remove photos** at any time — not locked to what was fetched initially.
- **Add "additional context"** — free text for anything not obvious from the photos themselves (texture, thickness, how something drapes). This gets folded into the AI vision garment description when a script is generated from this product.
- View the scraped description and source URL (read-only).

**Not yet tested against the real internet** — this development sandbox has no open-internet access, so the chain was validated against local mock pages (each method winning on its own, the manual fallback, total failure). It needs a real pass against TikTok Shop, Kalodata, and brand-website URLs to see which method each actually needs.

## How prompt generation works

On the Generator (the app's home screen), **+ New Script** pairs a character with a product from your two catalogues (only products that fetched successfully are selectable). That creates a draft script with a **Generate Prompt** button, which:

1. **Reads the photos with AI vision** (Claude, via the Anthropic API) to write three precise, concrete descriptions the SOP requires — none of these are typed in by hand:
   - **Garment** — colour, material, fit, hardware, trims, and any loose/free-moving element (a tie, a drape), read fresh from the product's photos (plus its "additional context" text, if any) every time a script generates.
   - **Persona** — hair, skin tone, build, visible accessories/tattoos (never facial features, since her face is never shown in the video) — read once from the character's identity photos and cached on the character.
   - **Setting** — the room, mirror, background, lighting — read once from the character's setting photos and cached on the character.

   The persona/setting descriptions are cached on the `Character` row so they're not re-read on every single script (per the SOP's own "garment analysis runs once per SKU" philosophy, extended to persona/setting since those are per-character, not per-product). They're automatically cleared and re-read the next time a prompt is generated if you change those photos — you never see or edit them directly, the same way you never see the original scraped page HTML.

2. **Assembles the full prompt deterministically** — no AI writes the actual movement/structure text. `generation/template.py` builds the locked 5-cut structure, the repeated anti-detachment language per cut, the anatomy/physics rules, and framing rules as a fixed template with the three AI-written descriptions dropped in. This is what makes the SOP's hard rules (three-quarter turns only, grip language restated every cut, etc.) guaranteed rather than hoped-for.

3. **Runs the SOP's Pre-Send Checklist automatically where it can be checked mechanically** (`generation/sop_check.py`) — most of these pass by construction since the template is fixed, but they're real regression protection if the template ever changes. The one substantive, content-dependent check is the **lingerie/sleepwear content-boundary rule (SOP §10)**: if the AI vision pass classifies the garment as lingerie/sleepwear/underwear, prompt generation is **hard-blocked** with a clear explanation — never generated and hoped nobody notices. A couple of checks the SOP itself says can't be automated (garment photos actually matching the real product; the rendered video's background staying identical, no glitches, ankles never appearing) are shown as manual items for you to confirm by eye, the first at prompt-review time and the second once you can actually watch the render.

4. **Shows the full prompt in an editable text box** alongside the checklist, so you can tweak it before approving. **Approve Prompt** saves your edits and marks the script `approved` — that becomes the prompt video generation submits to KIE.

If `ANTHROPIC_API_KEY` isn't set, Generate Prompt fails with a clear message telling you to add it — the product catalogue and character management are unaffected either way.

**Not yet tested with a real API key** — this development sandbox has no key configured, so the vision integration itself is validated via the graceful "not configured" error path plus the deterministic template/SOP-check logic (tested standalone with a realistic stubbed garment description, which read correctly and passed every automated check). The actual output quality of Claude's garment/persona/setting descriptions needs a real pass once you've added your key.

## How video generation works

Once a script's prompt is **approved**, its detail page shows a **Generate Video** button. This:

1. **Hosts reference photos publicly on catbox.moe.** KIE's video model can't reach anything on `localhost`, so before submitting, the character's setting photos and the product's photos are uploaded anonymously to [catbox.moe](https://catbox.moe) — no account or credentials, just a plain upload that returns a public URL. **Trade-off to know about:** these uploads are genuinely public and anonymous — anyone who has the exact URL can view the file, and there's no owner account to revoke access through later. Fine for this use case (fashion product/character photos, briefly hosted only so KIE can fetch them), but worth knowing. Identity photos aren't uploaded this way at all — identity is carried entirely by the character's KIE `character_id` instead (see below).

2. **Submits to KIE** (`POST /api/v1/jobs/createTask`, model `gemini-omni-video`) with the approved prompt text, the character's `kie_character_id`, and however many of those hosted image URLs fit KIE's shared 7-slot input quota (`images + character_ids ≤ 7`, and a character registered with a body reference photo — not just a portrait — costs 2 slots by itself). Setting photos are prioritized over garment photos when trimming to fit.

3. **Polls automatically** (`GET /api/v1/jobs/recordInfo`) with gentle exponential backoff (starting ~3s, capped at 15s, matching KIE's own guidance), showing live status — queued / generating / complete / failed — never leaving you guessing. Polling gives up after 15 minutes with a clear timeout message rather than spinning forever.

4. **Downloads the finished video immediately** once KIE reports success, rather than just linking to KIE's result URL — that URL expires roughly 24 hours after generation, so losing it before Phase 4 can save it to Drive would mean redoing the (expensive) generation step. The video then plays inline from the app's own copy.

### Characters need a KIE character ID first

KIE identity is handled through its own `character_ids` mechanism, separate from generic reference images. A character's profile has a **Register with KIE** button: it uploads that character's first 1-2 identity photos to catbox.moe (same as above), sends them to KIE's `gemini-omni-character` endpoint along with an AI-vision description of the character, and saves the returned character ID automatically — no manual copy-pasting. The **KIE Character ID** field itself stays editable too, for linking a character that was already created directly in KIE's own dashboard (its `kie_character_has_body` checkbox needs setting by hand in that case, since the app has no way to know how that one was registered). If a character has no KIE character ID set at all, Generate Video fails with a clear message telling you to add one — it doesn't silently skip identity or guess.

**Not yet tested with a real KIE task** — this sandbox has no `KIE_API_KEY` configured, and no network access to `api.kie.ai` or `catbox.moe` at all (checked both directly — blocked by this environment's policy, unlike `api.anthropic.com` which is allowlisted). So this was validated via the graceful "not configured"/upload-failure error paths (confirmed through the actual UI, and catbox's own network failure confirmed directly) and the image-quota math (unit-tested standalone). A real submission — both character registration and video generation, and in particular how well `gemini-omni-video` actually respects the SOP's hard rules from the prompt alone — needs a pass once you're running this locally with your key in place.

## Notes on the Character model

A character's core inputs are **name**, **characteristics** (free text), **character reference photos**, and **settings reference photos**. Physical traits (face, hair, skin tone, build, etc.) are read directly from the reference photos rather than entered as structured fields — `characteristics` is just additional context on top of that. (The AI-generated `persona_description` and `setting_description` mentioned above are a separate, internal thing — never a form field.) The one other field, **KIE Character ID**, is optional until you actually want to generate a video for that character — see **How video generation works** above.

- `setting` (reference photos of the filming location) is **locked as soon as a character is first saved**. Editing it later requires an explicit confirm step in the UI, since it changes the look of every future video with that character.

## What's needed from Andrew

- **`ANTHROPIC_API_KEY`** — prompt generation (Phase 2). Billed to your own Anthropic account.
- **`KIE_API_KEY`** — video generation (Phase 3). That's the only credential Phase 3 needs now — image hosting no longer requires any setup.
- **A KIE character ID per character** you want to generate video for — create it in KIE's own dashboard and paste it into that character's profile here, or use the **Register with KIE** button to have the app do it for you (see **How video generation works**).
- **Phase 4 (Drive save of finished videos)**: Google Drive credentials, and which Drive root the dated folders should be created under.
- **Real-world testing of product-fetch, prompt generation, and video generation**, all flagged above — this sandbox can reach `api.anthropic.com` but not `api.kie.ai`, `catbox.moe`, or the open internet in general (all checked directly — blocked here), so all three need a pass against real URLs/products/keys once you're running this locally.
