#!/usr/bin/env python3
"""
flock_news_scraper.py
=====================
Collects online news articles about Flock Safety cameras and produces a
structured JSON dataset.

For each article it collects:
    - publication_date   (ISO 8601 date, or null)
    - title              (article headline, or null)
    - media_outlet       (publisher/source name, or null)
    - url                (canonical article URL, or null)
    - content            (full article text, or a labeled short summary, or null)

Plus bookkeeping fields (content_source, access_status, retrieved_at, query,
content_char_count) that make the dataset auditable for research use.

Design notes / responsible-scraping choices
--------------------------------------------
* Discovery uses the public Google News RSS search endpoint (one feed per query
  string). This returns headline, publish date, source name, and a link.
* Every candidate article URL is checked against the site's robots.txt BEFORE
  fetching. If robots.txt disallows our user agent, we DO NOT fetch the page;
  we keep the RSS-provided title/date/outlet and store the RSS summary as the
  content, labeled content_source="rss_summary_robots_blocked".
* A polite delay (default 2s) and a descriptive User-Agent are used. Per-domain
  crawl-delay from robots.txt is respected when present.
* If a page is reachable but full text cannot be extracted (paywall, JS wall,
  extraction failure), we fall back to the RSS summary, clearly labeled.
* Duplicates are removed by canonical URL and by normalized title.
* Any field that cannot be determined is recorded as null.

IMPORTANT — network/egress:
    This script needs open outbound HTTPS to news sites and to
    news.google.com. It is intended to be run in an ordinary environment
    (e.g. your own computer). In restricted sandboxes where egress to news
    domains is blocked by policy, discovery/fetching will fail; run it
    somewhere with normal internet access.

Usage:
    python flock_news_scraper.py                      # default broad sweep
    python flock_news_scraper.py --max-per-query 100 --delay 2.0
    python flock_news_scraper.py --out ../data/flock_news_dataset.json

Dependencies:  feedparser, requests, trafilatura, beautifulsoup4,
               python-dateutil, lxml   (see requirements.txt)
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from urllib import robotparser

try:
    import feedparser
    import requests
    import trafilatura
    from bs4 import BeautifulSoup
    from dateutil import parser as dateparser
except ImportError as e:  # pragma: no cover
    sys.stderr.write(
        "Missing dependency: %s\nInstall with:  pip install -r requirements.txt\n" % e
    )
    raise

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

USER_AGENT = (
    "FlockNewsResearchBot/1.0 (academic research; contact: researcher@example.edu)"
)

# Search queries chosen to cast a broad net across outlets while staying on-topic.
DEFAULT_QUERIES = [
    '"Flock Safety" cameras',
    '"Flock Safety" license plate reader',
    'Flock cameras police surveillance',
    'Flock Safety privacy',
    'Flock Safety ALPR',
    'Flock Safety data sharing',
    'Flock Safety ICE immigration',
    'Flock Safety city council contract',
    'Flock Safety misuse police',
    'Flock camera lawsuit',
    'Flock Safety license plate reader ban',
    'Flock Safety audit accuracy',
]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref", "cmpid",
    "guccounter", "guce_referrer", "guce_referrer_sig",
}

log = logging.getLogger("flock_scraper")


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #

def canonicalize_url(url: str) -> str:
    """Strip tracking params and fragments so duplicate URLs collapse."""
    if not url:
        return url
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


def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = re.sub(r"\s+", " ", title).strip().lower()
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return t


def decode_google_news_url(google_url: str, session: requests.Session) -> str | None:
    """
    Resolve a news.google.com RSS link to the real article URL.

    Google has used several formats. We try, in order:
      1. base64-decode the article id and look for an embedded http(s) URL
         (works for older-style ids).
      2. follow the redirect with an HTTP request and read the final URL.
    Returns the resolved URL, or None if resolution fails.
    """
    if "news.google.com" not in google_url:
        return google_url
    # Attempt 1: decode the article id payload
    try:
        art_id = google_url.split("/articles/")[-1].split("?")[0]
        pad = art_id + "=" * (-len(art_id) % 4)
        raw = base64.urlsafe_b64decode(pad)
        matches = re.findall(rb"https?://[^\x00-\x1f\"'\\\s]+", raw)
        for m in matches:
            cand = m.decode("utf-8", "ignore")
            if "google.com" not in cand and len(cand) > 12:
                return cand
    except Exception:
        pass
    # Attempt 2: follow the redirect
    try:
        r = session.get(google_url, timeout=25, allow_redirects=True)
        if r.url and "news.google.com" not in r.url:
            return r.url
        # some responses embed the target in a meta refresh / anchor
        soup = BeautifulSoup(r.text, "lxml")
        a = soup.find("a", href=True)
        if a and "http" in a["href"] and "google.com" not in a["href"]:
            return a["href"]
    except Exception as e:
        log.debug("redirect resolution failed for %s: %s", google_url[:60], e)
    return None


# --------------------------------------------------------------------------- #
# robots.txt handling
# --------------------------------------------------------------------------- #

class RobotsCache:
    """Per-domain robots.txt cache with allow-checking and crawl-delay."""

    def __init__(self, session: requests.Session):
        self.session = session
        self._cache: dict[str, robotparser.RobotFileParser | None] = {}

    def _get_parser(self, url: str):
        domain = urlparse(url).netloc
        if domain in self._cache:
            return self._cache[domain]
        rp = robotparser.RobotFileParser()
        robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
        try:
            resp = self.session.get(robots_url, timeout=15)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp = None  # no robots.txt -> treat as allowed
        except Exception as e:
            log.debug("robots fetch failed for %s: %s", domain, e)
            rp = None
        self._cache[domain] = rp
        return rp

    def can_fetch(self, url: str) -> bool:
        rp = self._get_parser(url)
        if rp is None:
            return True
        try:
            return rp.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def crawl_delay(self, url: str) -> float | None:
        rp = self._get_parser(url)
        if rp is None:
            return None
        try:
            d = rp.crawl_delay(USER_AGENT)
            return float(d) if d else None
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

def extract_article(url: str, session: requests.Session) -> tuple[str | None, str | None, str | None]:
    """
    Fetch and extract (content, title, published_date_iso) from an article URL.
    Returns (None, None, None) on failure.
    """
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200 or not r.text:
            log.info("non-200 (%s) for %s", r.status_code, url)
            return None, None, None
        html = r.text
    except Exception as e:
        log.info("fetch failed for %s: %s", url, e)
        return None, None, None

    content = None
    title = None
    pub = None
    # trafilatura gives clean main-text extraction + metadata
    try:
        content = trafilatura.extract(
            html, include_comments=False, include_tables=False, favor_precision=True
        )
        meta = trafilatura.extract_metadata(html)
        if meta:
            title = meta.title or None
            if meta.date:
                pub = normalize_date(meta.date)
    except Exception as e:
        log.debug("trafilatura failed for %s: %s", url, e)

    # Fallbacks for title/date from OpenGraph / meta tags
    if not title or not pub:
        try:
            soup = BeautifulSoup(html, "lxml")
            if not title:
                og = soup.find("meta", property="og:title")
                title = (og["content"].strip() if og and og.get("content")
                         else (soup.title.string.strip() if soup.title else None))
            if not pub:
                for sel in [
                    ("meta", {"property": "article:published_time"}),
                    ("meta", {"name": "pubdate"}),
                    ("meta", {"name": "publishdate"}),
                    ("meta", {"itemprop": "datePublished"}),
                    ("time", {}),
                ]:
                    tag = soup.find(*[sel[0]], attrs=sel[1])
                    if tag:
                        val = tag.get("content") or tag.get("datetime") or tag.get_text()
                        pub = normalize_date(val)
                        if pub:
                            break
        except Exception as e:
            log.debug("bs4 fallback failed for %s: %s", url, e)

    return content, title, pub


def normalize_date(value) -> str | None:
    if not value:
        return None
    try:
        dt = dateparser.parse(str(value), fuzzy=True)
        if not dt:
            return None
        return dt.date().isoformat()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #

def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def gather_candidates(queries, max_per_query, session):
    """Query Google News RSS for each query; yield raw candidate records."""
    seen_feed_links = set()
    for q in queries:
        feed_url = GOOGLE_NEWS_RSS.format(q=requests.utils.quote(q))
        log.info("querying: %s", q)
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            log.warning("feed parse failed for %r: %s", q, e)
            continue
        log.info("  %d entries", len(feed.entries))
        for e in feed.entries[:max_per_query]:
            link = e.get("link")
            if not link or link in seen_feed_links:
                continue
            seen_feed_links.add(link)
            src = e.get("source", {})
            outlet = src.get("title") if isinstance(src, dict) else (src or None)
            summary = None
            if e.get("summary"):
                summary = BeautifulSoup(e["summary"], "lxml").get_text(" ", strip=True)
            yield {
                "query": q,
                "google_link": link,
                "title": e.get("title"),
                "published_date": normalize_date(e.get("published")),
                "media_outlet": outlet,
                "rss_summary": summary,
            }


def run(args):
    session = build_session()
    robots = RobotsCache(session)

    raw_records = list(
        gather_candidates(args.queries, args.max_per_query, session)
    )
    log.info("collected %d raw candidates", len(raw_records))

    dataset = []
    seen_urls = set()
    seen_titles = set()
    last_fetch_by_domain: dict[str, float] = {}

    for i, rec in enumerate(raw_records, 1):
        real_url = decode_google_news_url(rec["google_link"], session)
        url = canonicalize_url(real_url) if real_url else None

        # Deduplicate
        title_key = normalize_title(rec.get("title") or "")
        if url and url in seen_urls:
            log.info("[%d] dup url, skipping: %s", i, url)
            continue
        if title_key and title_key in seen_titles:
            log.info("[%d] dup title, skipping: %s", i, rec.get("title"))
            continue

        content = None
        content_source = None
        access_status = "unknown"

        if url:
            allowed = robots.can_fetch(url)
            if not allowed:
                access_status = "robots_disallowed"
                content = rec.get("rss_summary")
                content_source = "rss_summary_robots_blocked" if content else None
                log.info("[%d] robots.txt disallows fetch: %s", i, url)
            else:
                # polite per-domain rate limiting
                domain = urlparse(url).netloc
                delay = robots.crawl_delay(url) or args.delay
                elapsed = time.time() - last_fetch_by_domain.get(domain, 0)
                if elapsed < delay:
                    time.sleep(delay - elapsed)
                last_fetch_by_domain[domain] = time.time()

                content, ex_title, ex_pub = extract_article(url, session)
                if content and len(content.strip()) >= args.min_content_chars:
                    content_source = "full_text"
                    access_status = "ok"
                    if not rec.get("title") and ex_title:
                        rec["title"] = ex_title
                    if not rec.get("published_date") and ex_pub:
                        rec["published_date"] = ex_pub
                else:
                    # reachable but no usable text -> labeled summary fallback
                    content = rec.get("rss_summary")
                    content_source = "rss_summary_no_fulltext" if content else None
                    access_status = "no_fulltext"
        else:
            access_status = "url_unresolved"
            content = rec.get("rss_summary")
            content_source = "rss_summary_url_unresolved" if content else None

        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)

        dataset.append({
            "publication_date": rec.get("published_date") or None,
            "title": rec.get("title") or None,
            "media_outlet": rec.get("media_outlet") or None,
            "url": url or None,
            "content": content or None,
            "content_source": content_source,          # how 'content' was obtained
            "access_status": access_status,             # ok / robots_disallowed / ...
            "content_char_count": len(content) if content else 0,
            "search_query": rec.get("query"),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
        log.info("[%d] %-22s %s", i, access_status, (url or rec.get("title") or "")[:70])

    # Write outputs
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    payload = {
        "dataset_name": "Flock Safety news dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "flock_news_scraper.py",
        "record_count": len(dataset),
        "field_notes": {
            "publication_date": "ISO date or null",
            "title": "headline or null",
            "media_outlet": "publisher name or null",
            "url": "canonical article URL or null",
            "content": "full text, a labeled summary, or null",
            "content_source": "full_text | rss_summary_* | null (labels partial/summary content)",
            "access_status": "ok | robots_disallowed | no_fulltext | url_unresolved | unknown",
        },
        "articles": dataset,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("wrote %d articles to %s", len(dataset), args.out)


def parse_args(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Scrape Flock Safety news into JSON.")
    ap.add_argument("--out", default=os.path.join(here, "..", "data", "flock_news_dataset.json"))
    ap.add_argument("--log", default=os.path.join(here, "..", "logs", "scraper.log"))
    ap.add_argument("--max-per-query", type=int, default=100)
    ap.add_argument("--delay", type=float, default=2.0, help="default politeness delay (s)")
    ap.add_argument("--min-content-chars", type=int, default=400)
    ap.add_argument("--queries", nargs="*", default=DEFAULT_QUERIES)
    return ap.parse_args(argv)


def setup_logging(log_path):
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.log)
    log.info("=== flock_news_scraper start ===")
    log.info("queries=%d max_per_query=%d delay=%.1fs", len(args.queries), args.max_per_query, args.delay)
    try:
        run(args)
    except Exception:
        log.exception("fatal error")
        raise
    log.info("=== flock_news_scraper done ===")


if __name__ == "__main__":
    main()
