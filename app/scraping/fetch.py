"""
Orchestrates the product-fetch fallback chain: try each method in order until one
finds usable product images, and if none of them do, build a plain-English summary
of what was tried and why it didn't work.
"""

from app.scraping.methods import (
    METHOD_LABELS,
    FetchResult,
    fetch_headless_browser,
    fetch_html_scrape,
    fetch_structured_data,
)

METHODS = [fetch_structured_data, fetch_html_scrape, fetch_headless_browser]


def fetch_product(url: str) -> tuple[FetchResult | None, list[FetchResult]]:
    """Try each fetch method in order. Returns (winning_result, all_attempts).
    winning_result is None if every method failed to find images."""
    attempts: list[FetchResult] = []
    for method_fn in METHODS:
        result = method_fn(url)
        attempts.append(result)
        if result.success and result.images:
            return result, attempts
    return None, attempts


def build_failure_message(url: str, attempts: list[FetchResult]) -> str:
    lines = [f"Couldn't automatically pull product images from {url}. Tried {len(attempts)} method(s):"]
    for i, attempt in enumerate(attempts, start=1):
        label = METHOD_LABELS.get(attempt.method, attempt.method)
        reason = attempt.error or "found no images"
        lines.append(f"{i}. {label} — {reason}.")
    return "\n".join(lines)
