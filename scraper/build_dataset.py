#!/usr/bin/env python3
"""
build_dataset.py
================
Processing pipeline for the Flock Safety news dataset.

This is the second half of the Task 2 pipeline. It takes RAW collected
records (data/raw_collected.json) and produces the clean, structured,
deduplicated JSON dataset (data/flock_news_dataset.json) plus a run log.

Why a separate step?
    The live-fetching scraper (flock_news_scraper.py) needs open internet
    access to news sites. In the restricted build environment used to produce
    the delivered dataset, outbound access to news domains was blocked by the
    organization's egress policy, so article records were gathered through the
    project's sanctioned research tooling and written to raw_collected.json.
    This script performs the SAME normalization, deduplication, and schema
    enforcement the scraper applies, so the delivered dataset is produced by
    real, inspectable code.

It enforces the required schema for every article:
    publication_date, title, media_outlet, url, content   (+ audit fields)
missing values are recorded as null, duplicates removed, and partial /
summary content is clearly labeled via `content_source`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(HERE, "..", "data", "raw_collected.json")
OUT_PATH = os.path.join(HERE, "..", "data", "flock_news_dataset.json")
LOG_PATH = os.path.join(HERE, "..", "logs", "build_dataset.log")

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref", "cmpid",
}

# Map the raw "access" note to a normalized access_status and content_source.
ACCESS_TO_STATUS = {
    "full": "ok",
    "partial": "partial",
    "paywalled": "paywalled",
    "robots_disallowed": "robots_disallowed",
    "http_error_403": "http_error",
    "unavailable": "unavailable",
}

log = logging.getLogger("build_dataset")


def setup_logging():
    os.makedirs(os.path.dirname(os.path.abspath(LOG_PATH)), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def canonicalize_url(url):
    if not url:
        return None
    try:
        p = urlparse(url)
        q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING_PARAMS]
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme or "https", netloc, path, "", urlencode(q), ""))
    except Exception:
        return url


def normalize_title(title):
    if not title:
        return ""
    t = re.sub(r"\s+", " ", title).strip().lower()
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return t


def normalize_date(value):
    """Accept ISO or common formats; return yyyy-mm-dd or None."""
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if m:
        y, mo, d = m.groups()
        try:
            return datetime(int(y), int(mo), int(d)).date().isoformat()
        except ValueError:
            return None
    return None


def content_source_label(raw):
    """Decide the content_source label for a record."""
    method = raw.get("collection_method")
    access = raw.get("access")
    if not raw.get("content"):
        return None
    if method == "web_extracted_summary":
        if access == "paywalled":
            return "extracted_summary_paywalled"
        return "extracted_summary"
    if method == "full_text":
        return "full_text"
    return method or "extracted_summary"


def main():
    setup_logging()
    log.info("=== build_dataset start ===")

    with open(RAW_PATH, encoding="utf-8") as f:
        raw_records = json.load(f)
    log.info("loaded %d raw records from %s", len(raw_records), os.path.basename(RAW_PATH))

    dataset = []
    seen_urls = set()
    seen_titles = set()
    stats = {
        "raw": len(raw_records),
        "dup_url": 0,
        "dup_title": 0,
        "kept": 0,
        "content_null": 0,
        "date_null": 0,
    }

    for i, raw in enumerate(raw_records, 1):
        url = canonicalize_url(raw.get("url"))
        title = (raw.get("title") or "").strip() or None
        title_key = normalize_title(title or "")

        # Deduplicate by canonical URL, then by normalized title.
        if url and url in seen_urls:
            stats["dup_url"] += 1
            log.info("[%d] duplicate URL removed: %s", i, url)
            continue
        if title_key and title_key in seen_titles:
            stats["dup_title"] += 1
            log.info("[%d] duplicate title removed: %s", i, title)
            continue
        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)

        content = raw.get("content")
        if isinstance(content, str):
            content = content.strip() or None

        access_status = ACCESS_TO_STATUS.get(raw.get("access"), "unknown")
        record = {
            # --- required fields (missing -> null) ---
            "publication_date": normalize_date(raw.get("publication_date")),
            "title": title,
            "media_outlet": (raw.get("media_outlet") or None),
            "url": url,
            "content": content,
            # --- audit / provenance fields ---
            "author": raw.get("author") or None,
            "content_source": content_source_label(raw),
            "access_status": access_status,
            "content_char_count": len(content) if content else 0,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
        if record["content"] is None:
            stats["content_null"] += 1
        if record["publication_date"] is None:
            stats["date_null"] += 1

        dataset.append(record)
        stats["kept"] += 1
        log.info("[%d] kept %-18s %s", i, access_status, (url or title or "")[:72])

    # Sort newest-first by publication date (None dates sink to the end).
    dataset.sort(key=lambda r: (r["publication_date"] or "0000-00-00"), reverse=True)

    # Outlet distribution (useful for research provenance).
    outlets = {}
    for r in dataset:
        outlets[r["media_outlet"] or "Unknown"] = outlets.get(r["media_outlet"] or "Unknown", 0) + 1

    payload = {
        "dataset_name": "Flock Safety news dataset",
        "topic": "News coverage of Flock Safety cameras / automated license plate readers",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "build_dataset.py (pipeline shared with flock_news_scraper.py)",
        "record_count": len(dataset),
        "distinct_outlets": len(outlets),
        "schema": {
            "publication_date": "ISO date (yyyy-mm-dd) or null",
            "title": "article headline or null",
            "media_outlet": "publisher / source name or null",
            "url": "canonical article URL or null",
            "content": "article text or a clearly-labeled summary, or null",
            "author": "byline or null",
            "content_source": "full_text | extracted_summary | extracted_summary_paywalled | null",
            "access_status": "ok | partial | paywalled | robots_disallowed | http_error | unavailable | unknown",
            "content_char_count": "integer length of content (0 if null)",
            "retrieved_at": "UTC timestamp when the record was assembled",
        },
        "collection_notes": (
            "Duplicates removed by canonical URL and normalized title. Missing "
            "values recorded as null. Where full article text could not be "
            "retrieved (robots.txt disallow, HTTP error, or paywall), content is "
            "either null or a clearly-labeled summary (see content_source / "
            "access_status). Summaries in this delivered dataset were produced "
            "from the live page via sanctioned research tooling because the build "
            "environment blocked direct outbound access to news sites; the "
            "companion flock_news_scraper.py performs raw full-text extraction "
            "when run in an environment with open internet access."
        ),
        "outlet_distribution": dict(sorted(outlets.items(), key=lambda kv: -kv[1])),
        "articles": dataset,
    }

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    log.info("---- summary ----")
    for k, v in stats.items():
        log.info("  %-12s %s", k, v)
    log.info("  distinct_outlets %s", len(outlets))
    log.info("wrote %d articles to %s", len(dataset), os.path.basename(OUT_PATH))
    log.info("=== build_dataset done ===")


if __name__ == "__main__":
    main()
