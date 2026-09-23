"""
Individual product-fetch methods, tried in order (cheapest/most reliable first) by
app.scraping.fetch.fetch_product. Each method is independent and self-contained: it
takes a URL and returns a FetchResult describing either what it found or why it
couldn't find anything, in a message a person can read.
"""

import json
import os
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Filename fragments that mean "this is chrome, not the product" — logos, icons, tracking pixels.
NON_PRODUCT_HINTS = ("logo", "icon", "sprite", "favicon", "pixel", "spinner", "placeholder", "avatar")


@dataclass
class FetchResult:
    method: str
    success: bool = False
    images: list = field(default_factory=list)
    title: str = ""
    description: str = ""
    error: str = ""


METHOD_LABELS = {
    "structured_data": "reading the page's structured product data",
    "html_scrape": "scanning the page's raw HTML for product images",
    "headless_browser": "rendering the page in a real browser",
}


def _dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _looks_like_product_image(url: str) -> bool:
    lower = url.lower()
    if lower.endswith(".svg"):
        return False
    if any(hint in lower for hint in NON_PRODUCT_HINTS):
        return False
    return True


def _extract_from_html(html: str, base_url: str, broad: bool) -> FetchResult:
    """Shared extraction logic for both the plain-HTTP and headless-browser methods."""
    soup = BeautifulSoup(html, "html.parser")

    images: list[str] = []
    title = ""
    description = ""

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            if item_type == "Product" or (isinstance(item_type, list) and "Product" in item_type):
                title = title or item.get("name", "") or ""
                description = description or item.get("description", "") or ""
                img = item.get("image")
                if isinstance(img, str):
                    images.append(img)
                elif isinstance(img, list):
                    images.extend([i for i in img if isinstance(i, str)])
                elif isinstance(img, dict) and img.get("url"):
                    images.append(img["url"])

    og_images = [m.get("content") for m in soup.find_all("meta", property="og:image") if m.get("content")]
    images.extend(og_images)

    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"]
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()

    if not description:
        for attrs in ({"property": "og:description"}, {"name": "description"}):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                description = tag["content"]
                break

    if broad and not images:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-srcset") or ""
            src = src.split(" ")[0].split(",")[0].strip()
            if src:
                images.append(src)

    images = [urljoin(base_url, u) for u in images]
    images = [u for u in images if _looks_like_product_image(u)]
    images = _dedupe(images)[:12]

    return FetchResult(
        method="",  # filled in by caller
        success=bool(images),
        images=images,
        title=title.strip(),
        description=description.strip(),
    )


def fetch_structured_data(url: str, timeout: float = 10.0) -> FetchResult:
    """Fast path: one plain HTTP GET, looking only at schema.org JSON-LD and Open Graph tags.
    Works for most modern storefronts (Shopify etc.) without executing any JS."""
    try:
        resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
    except httpx.TimeoutException:
        return FetchResult(method="structured_data", error="the request timed out")
    except httpx.RequestError as e:
        return FetchResult(method="structured_data", error=f"the request failed ({e.__class__.__name__})")

    if resp.status_code >= 400:
        return FetchResult(method="structured_data", error=f"the site returned HTTP {resp.status_code}")

    result = _extract_from_html(resp.text, str(resp.url), broad=False)
    result.method = "structured_data"
    if not result.success:
        result.error = "no product schema (JSON-LD) or Open Graph images found on the page"
    return result


def fetch_html_scrape(url: str, timeout: float = 10.0) -> FetchResult:
    """Broader plain-HTTP path: scans every <img> tag in the raw HTML. Catches simpler
    sites that don't publish structured data but still render images server-side."""
    try:
        resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
    except httpx.TimeoutException:
        return FetchResult(method="html_scrape", error="the request timed out")
    except httpx.RequestError as e:
        return FetchResult(method="html_scrape", error=f"the request failed ({e.__class__.__name__})")

    if resp.status_code >= 400:
        return FetchResult(method="html_scrape", error=f"the site returned HTTP {resp.status_code}")

    result = _extract_from_html(resp.text, str(resp.url), broad=True)
    result.method = "html_scrape"
    if not result.success:
        result.error = "no usable <img> tags found in the raw page HTML — the page is likely rendered client-side"
    return result


def fetch_headless_browser(url: str, timeout_ms: int = 20000) -> FetchResult:
    """Slowest, most capable path: actually renders the page in Chromium, for
    JS-heavy storefronts (TikTok Shop and similar) that return near-empty HTML
    to a plain HTTP request."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return FetchResult(method="headless_browser", error="the headless browser isn't installed")

    executable_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None

    try:
        with sync_playwright() as p:
            launch_kwargs = {"headless": True}
            if executable_path:
                launch_kwargs["executable_path"] = executable_path
            browser = p.chromium.launch(**launch_kwargs)
            try:
                page = browser.new_page(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900})
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                html = page.content()
                page_title = page.title()
            finally:
                browser.close()
    except Exception as e:  # noqa: BLE001 — surfacing to the user, not handling specific cases
        detail = str(e).strip().splitlines()[0] if str(e).strip() else e.__class__.__name__
        return FetchResult(method="headless_browser", error=f"the browser couldn't load the page ({detail})")

    result = _extract_from_html(html, url, broad=True)
    result.method = "headless_browser"
    if not result.title:
        result.title = page_title or ""
    if not result.success:
        result.error = "rendered the page fully but still found no usable product images — the site may be blocking automated access"
    return result
