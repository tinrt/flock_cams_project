#!/usr/bin/env python3
"""
build_atlas_alpr_launch_dates.py

Build a police-department/agency-level ALPR adoption timing dataset from the
Atlas of Surveillance CSV already stored in this project.

The script is deliberately conservative:
- It extracts launch/adoption timing from the Atlas Summary text.
- It distinguishes strong launch language ("began using", "since", "installed")
  from weaker evidence ("purchased", "approved contract", "as of").
- It does NOT automatically treat Link Date as the launch date.
- It keeps the original Summary and source links so every result is auditable.
- Ambiguous rows are flagged for manual review rather than guessed.

Run from the flock_cams_project root:
    python scraper/build_atlas_alpr_launch_dates.py

Optional:
    python scraper/build_atlas_alpr_launch_dates.py --police-only
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_INPUT = Path(
    "data/Atlas of Surveillance-Automated License Plate Readers-20260911.csv"
)
DEFAULT_OUTPUT = Path("data/atlas_alpr_agency_launch_dates.csv")
DEFAULT_REVIEW = Path("data/atlas_alpr_agency_launch_dates_manual_review.csv")

MONTHS = (
    r"January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?"
)

# Ordered from strongest launch/use evidence to weaker timing proxies.
PATTERNS = [
    # Exact/near-exact start of use.
    ("first_use", "high",
     rf"\b(?:has\s+)?(?:been\s+)?(?:using|used|operated)\b[^.!?\n]{{0,100}}?\b(?:since|starting|beginning)\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})"),
    ("first_use", "high",
     rf"\b(?:began|started|commenced)\s+(?:using|operating|deploying)\b[^.!?\n]{{0,100}}?(?:\bin\b|\bsince\b)?\s*(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})"),
    ("first_use", "high",
     rf"\b(?:has\s+)?(?:used|operated)\b[^.!?\n]{{0,100}}?\bsince\s+(?:at\s+least\s+)?(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})"),
    ("first_known_use", "medium_high",
     rf"\b(?:has\s+)?(?:used|operated)\b[^.!?\n]{{0,100}}?\bsince\s+at\s+least\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})"),

    # Installation/deployment.
    ("installation", "high",
     rf"\b(?:installed|deployed|launched)\b[^.!?\n]{{0,100}}?\b(?:in|on|during)\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})"),
    ("installation", "high",
     rf"\b(?:in|during)\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})[^.!?\n]{{0,100}}?\b(?:installed|deployed|launched)\b"),

    # Acquisition: useful but not necessarily operational launch.
    ("purchase", "medium",
     rf"\b(?:purchased|acquired|bought|spent|outfitted)\b[^.!?\n]{{0,120}}?\b(?:in|during)\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})"),
    ("purchase", "medium",
     rf"\b(?:in|during)\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})[^.!?\n]{{0,120}}?\b(?:purchased|acquired|bought|spent|outfitted)\b"),

    # Contract/approval: adoption proxy, not operational date.
    ("contract_or_approval", "medium",
     rf"\b(?:approved|signed|entered|awarded)\b[^.!?\n]{{0,120}}?\b(?:contract|agreement|purchase)\b[^.!?\n]{{0,80}}?\b(?:in|during)\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})"),
    ("contract_or_approval", "medium",
     rf"\b(?:in|during)\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})[^.!?\n]{{0,120}}?\b(?:approved|signed|entered|awarded)\b[^.!?\n]{{0,100}}?\b(?:contract|agreement|purchase)\b"),

    # Weak: only proves technology existed by this time.
    ("known_by", "low",
     rf"\bas\s+of\s+(?P<date>(?:{MONTHS})\s+\d{{4}}|\d{{4}})"),
]

COMPILED = [
    (kind, confidence, re.compile(pattern, re.I))
    for kind, confidence, pattern in PATTERNS
]

# Prefer direct use/deployment over purchase/contract/as-of evidence.
TYPE_RANK = {
    "first_use": 0,
    "first_known_use": 1,
    "installation": 2,
    "purchase": 3,
    "contract_or_approval": 4,
    "known_by": 5,
}

CONFIDENCE_RANK = {
    "high": 0,
    "medium_high": 1,
    "medium": 2,
    "low": 3,
    "none": 4,
}


def clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse_date_text(text: str) -> Tuple[str, str]:
    """Return normalized YYYY-MM when month exists, otherwise YYYY."""
    text = clean(text)
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    if not year_match:
        return "", ""

    year = year_match.group(0)
    month = ""

    for fmt in ("%B %Y", "%b %Y"):
        try:
            dt = datetime.strptime(text, fmt)
            month = f"{dt.month:02d}"
            break
        except ValueError:
            pass

    normalized = f"{year}-{month}" if month else year
    return normalized, year


def sentence_around(text: str, start: int, end: int) -> str:
    left = max(
        text.rfind(".", 0, start),
        text.rfind("\n", 0, start),
        text.rfind(";", 0, start),
    )
    right_candidates = [
        x for x in (
            text.find(".", end),
            text.find("\n", end),
            text.find(";", end),
        )
        if x != -1
    ]
    right = min(right_candidates) if right_candidates else len(text)
    return clean(text[left + 1:right + 1])


def extract_candidates(summary: str) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []

    for kind, confidence, regex in COMPILED:
        for match in regex.finditer(summary):
            raw_date = clean(match.group("date"))
            normalized, year = parse_date_text(raw_date)
            if not year:
                continue

            candidates.append({
                "date_type": kind,
                "confidence": confidence,
                "date_raw": raw_date,
                "date_normalized": normalized,
                "year": year,
                "evidence": sentence_around(summary, match.start(), match.end()),
                "match_start": str(match.start()),
            })

    # De-duplicate exact logical matches.
    unique = {}
    for c in candidates:
        key = (
            c["date_type"],
            c["date_normalized"],
            c["evidence"].lower(),
        )
        unique[key] = c

    return list(unique.values())


def choose_candidate(candidates: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if not candidates:
        return None

    # Primary objective is launch/use timing. We prefer stronger semantic types,
    # then earlier dates within that type, then confidence.
    return sorted(
        candidates,
        key=lambda c: (
            TYPE_RANK.get(c["date_type"], 99),
            c["date_normalized"],
            CONFIDENCE_RANK.get(c["confidence"], 99),
            int(c["match_start"]),
        ),
    )[0]


def source_for_evidence(row: Dict[str, str], chosen: Optional[Dict[str, str]]) -> Tuple[str, str, str]:
    """
    Atlas summaries do not map individual clauses to links mechanically.
    Preserve all three source links; also return the earliest dated source
    as a convenience, without claiming its date is the launch date.
    """
    sources = []
    for i in (1, 2, 3):
        url = clean(row.get(f"Link {i}"))
        date = clean(row.get(f"Link {i} Date"))
        name = clean(row.get(f"Link {i} Source"))
        if url:
            sources.append((date, url, name))

    dated = []
    for date, url, name in sources:
        parsed = None
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%d/%y", "%m/%d/%Y"):
            try:
                parsed = datetime.strptime(date, fmt)
                break
            except ValueError:
                pass
        if parsed:
            dated.append((parsed, url, name))

    if dated:
        dated.sort(key=lambda x: x[0])
        return dated[0][1], dated[0][2], dated[0][0].date().isoformat()

    if sources:
        return sources[0][1], sources[0][2], ""

    return "", "", ""


def process_row(row: Dict[str, str]) -> Dict[str, str]:
    summary = clean(row.get("Summary"))
    candidates = extract_candidates(summary)
    chosen = choose_candidate(candidates)

    source_url, source_name, source_date = source_for_evidence(row, chosen)

    # Conservative interpretation labels.
    if chosen:
        launch_date = chosen["date_normalized"]
        launch_year = chosen["year"]
        date_type = chosen["date_type"]
        confidence = chosen["confidence"]
        evidence = chosen["evidence"]
    else:
        launch_date = ""
        launch_year = ""
        date_type = "not_found"
        confidence = "none"
        evidence = ""

    # Whether this is suitable as treatment timing without manual review.
    # Strong first-use/installation language is the safest automated category.
    usable_directly = (
        date_type in {"first_use", "first_known_use", "installation"}
        and confidence in {"high", "medium_high"}
    )

    needs_review = (
        not usable_directly
        or len(candidates) > 1
    )

    return {
        "aos_number": clean(row.get("AOSNUMBER")),
        "ori9": clean(row.get("NEWAOSNUMBER (ORI9)")),
        "agency": clean(row.get("Agency")),
        "agency_type": clean(row.get("Type of LEA")),
        "city": clean(row.get("City")),
        "county": clean(row.get("County")),
        "state": clean(row.get("State")),
        "jurisdiction_type": clean(row.get("Type of Juris")),
        "technology": clean(row.get("Technology")),
        "vendor": clean(row.get("Vendor")),

        "alpr_start_date": launch_date,
        "alpr_start_year": launch_year,
        "date_type": date_type,
        "confidence": confidence,
        "usable_as_launch_timing_without_review": str(usable_directly),
        "needs_manual_review": str(needs_review),

        "date_evidence": evidence,
        "atlas_summary": summary,

        "link_1": clean(row.get("Link 1")),
        "link_1_source": clean(row.get("Link 1 Source")),
        "link_1_date": clean(row.get("Link 1 Date")),
        "link_2": clean(row.get("Link 2")),
        "link_2_source": clean(row.get("Link 2 Source")),
        "link_2_date": clean(row.get("Link 2 Date")),
        "link_3": clean(row.get("Link 3")),
        "link_3_source": clean(row.get("Link 3 Source")),
        "link_3_date": clean(row.get("Link 3 Date")),

        "earliest_dated_source_url": source_url,
        "earliest_dated_source_name": source_name,
        "earliest_dated_source_date": source_date,

        "candidate_count": str(len(candidates)),
        "all_date_candidates": " | ".join(
            f"{c['date_type']}:{c['date_normalized']}:{c['evidence']}"
            for c in sorted(
                candidates,
                key=lambda x: (x["date_normalized"], TYPE_RANK.get(x["date_type"], 99))
            )
        ),
    }


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract agency-level ALPR adoption timing from Atlas of Surveillance."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--review-output", default=str(DEFAULT_REVIEW))
    parser.add_argument(
        "--police-only",
        action="store_true",
        help="Keep only rows where Type of LEA is Police.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(
            f"Atlas CSV not found: {input_path}\n"
            "Run this script from the flock_cams_project repository root, "
            "or pass --input PATH."
        )

    with input_path.open("r", newline="", encoding="utf-8-sig") as f:
        source_rows = list(csv.DictReader(f))

    results: List[Dict[str, str]] = []

    for row in source_rows:
        if clean(row.get("Technology")).lower() != "automated license plate readers":
            continue

        if args.police_only and clean(row.get("Type of LEA")).lower() != "police":
            continue

        results.append(process_row(row))

    # Stable ordering for reproducibility.
    results.sort(
        key=lambda r: (
            r["state"],
            r["city"],
            r["agency"],
            r["aos_number"],
        )
    )

    output_path = Path(args.output)
    review_path = Path(args.review_output)

    write_csv(output_path, results)

    review_rows = [
        r for r in results
        if r["needs_manual_review"] == "True"
    ]
    write_csv(review_path, review_rows)

    found = [r for r in results if r["alpr_start_year"]]
    direct = [
        r for r in results
        if r["usable_as_launch_timing_without_review"] == "True"
    ]

    print(f"Atlas ALPR rows processed: {len(results):,}")
    print(f"Rows with a timing signal: {len(found):,}")
    print(f"Strong first-use/deployment timing: {len(direct):,}")
    print(f"Rows needing manual review: {len(review_rows):,}")
    print()
    print(f"Main dataset:   {output_path}")
    print(f"Review dataset: {review_path}")
    print()
    print(
        "IMPORTANT: alpr_start_date is based on the Atlas summary language. "
        "Rows marked usable_as_launch_timing_without_review=False should not "
        "be treated as launch dates until reviewed."
    )


if __name__ == "__main__":
    main()
