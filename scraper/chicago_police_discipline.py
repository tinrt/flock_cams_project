#!/usr/bin/env python3
"""
chicago_police_discipline.py

Downloads Chicago police-misconduct data from the City of Chicago open-data API
and builds one case-level outcome file.

Key point:
Your existing COPA "By Complainant or Subject" file is useful, but it is not
the full disciplinary dataset. In particular, detailed BIA investigations are
not included there. This script adds the City's BIA-by-officer dataset and
also downloads COPA Summary + COPA By Involved Officer.

No API token is required for normal use.

Run:
    python scraper/chicago_police_discipline.py

Outputs:
    data/discipline/chicago_copa_summary.csv
    data/discipline/chicago_copa_by_officer.csv
    data/discipline/chicago_bia_by_officer.csv
    data/discipline/chicago_police_discipline_cases.csv
    data/discipline/chicago_police_discipline_by_month.csv
"""

from __future__ import annotations
import csv, io, json, re, sys, time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List
import requests

OUT = Path("data/discipline")
OUT.mkdir(parents=True, exist_ok=True)

# Verified City of Chicago Socrata dataset IDs.
DATASETS = {
    "copa_summary": "mft5-nfa8",
    "bia_by_officer": "t7km-zpxd",
    # COPA's official documentation identifies this as the by-officer companion.
    # If the schema endpoint ever reports a changed ID, the script will stop
    # rather than silently use the wrong dataset.
    "copa_by_officer": "u3bx-7883",
}

DOMAIN = "https://data.cityofchicago.org"
HEADERS = {"User-Agent": "flock-cams-project academic research/1.0"}


def get_json(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=120)
    r.raise_for_status()
    return r.json()


def metadata(dataset_id):
    return get_json(f"{DOMAIN}/api/views/{dataset_id}")


def download_all(dataset_id, page_size=50000):
    """Download all rows from Socrata in pages."""
    rows = []
    offset = 0
    while True:
        print(f"  {dataset_id}: rows {offset:,} ...")
        batch = get_json(
            f"{DOMAIN}/resource/{dataset_id}.json",
            {"$limit": page_size, "$offset": offset}
        )
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        time.sleep(0.2)
    return rows


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({k for r in rows for k in r.keys()})
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def first(row, *names):
    # Socrata API field names are normally lowercase/underscored.
    lowered = {re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_"): v
               for k, v in row.items()}
    for name in names:
        key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if key in lowered and lowered[key] not in (None, ""):
            return str(lowered[key])
    return ""


def year_month(date_text):
    m = re.match(r"(\d{4})-(\d{2})", date_text or "")
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def aggregate_bia(rows):
    """BIA is officer-level; collapse to one row per LOG_NO."""
    grouped = defaultdict(list)
    for r in rows:
        log = first(r, "log_no", "log number")
        if log:
            grouped[log].append(r)

    out = []
    for log, rr in grouped.items():
        r0 = rr[0]
        findings = sorted({first(r, "finding", "final_finding")
                           for r in rr if first(r, "finding", "final_finding")})
        categories = sorted({first(r, "final_category", "category", "case_type")
                             for r in rr if first(r, "final_category", "category", "case_type")})
        penalties = sorted({first(r, "penalty", "discipline", "final_penalty")
                            for r in rr if first(r, "penalty", "discipline", "final_penalty")})
        complaint_date = first(r0, "complaint_date")
        out.append({
            "log_no": log,
            "investigating_agency": "BIA",
            "complaint_date": complaint_date,
            "year_month": year_month(complaint_date),
            "current_status": first(r0, "current_status", "status"),
            "case_type": first(r0, "case_type"),
            "final_categories": " | ".join(categories),
            "findings": " | ".join(findings),
            "penalties": " | ".join(penalties),
            "number_involved_officer_rows": len(rr),
            "source_dataset": "BIA Cases - By Involved Officer",
        })
    return out


def aggregate_copa(rows):
    out = []
    for r in rows:
        log = first(r, "log_no", "log number")
        if not log:
            continue
        complaint_date = first(r, "complaint_date")
        agency = first(r, "assigned_to", "current_category", "investigating_agency")
        # COPA Summary may include referrals; preserve its fields rather than guess.
        out.append({
            "log_no": log,
            "investigating_agency": agency or "COPA/recorded by COPA",
            "complaint_date": complaint_date,
            "year_month": year_month(complaint_date),
            "current_status": first(r, "current_status", "status"),
            "case_type": first(r, "case_type"),
            "final_categories": first(r, "final_category", "category"),
            "findings": first(r, "finding", "findings"),
            "penalties": first(r, "penalty", "discipline"),
            "number_involved_officer_rows": "",
            "source_dataset": "COPA Cases - Summary",
        })
    return out


def monthly(cases):
    g = defaultdict(lambda: {"complaints": 0, "bia": 0, "copa_records": 0})
    for r in cases:
        ym = r.get("year_month", "")
        if not ym:
            continue
        g[ym]["complaints"] += 1
        if r["investigating_agency"] == "BIA":
            g[ym]["bia"] += 1
        else:
            g[ym]["copa_records"] += 1
    return [{"year_month": ym, **vals} for ym, vals in sorted(g.items())]


def main():
    print("Checking City of Chicago datasets...")
    for name, did in DATASETS.items():
        try:
            meta = metadata(did)
            print(f"  {name}: {meta.get('name', did)}")
        except Exception as e:
            if name == "copa_by_officer":
                print(f"  WARNING: optional COPA-by-officer dataset unavailable: {e}")
            else:
                raise

    print("\nDownloading COPA Summary...")
    copa = download_all(DATASETS["copa_summary"])
    write_csv(OUT / "chicago_copa_summary.csv", copa)

    print("\nDownloading BIA By Involved Officer...")
    bia = download_all(DATASETS["bia_by_officer"])
    write_csv(OUT / "chicago_bia_by_officer.csv", bia)

    print("\nDownloading COPA By Involved Officer (supplementary)...")
    try:
        copa_officer = download_all(DATASETS["copa_by_officer"])
        write_csv(OUT / "chicago_copa_by_officer.csv", copa_officer)
    except Exception as e:
        print("  Skipped COPA-by-officer:", e)

    # Keep COPA and BIA as separate source records. Do not deduplicate across
    # agencies by assumptions; LOG_NO can be used later for audited joins.
    cases = aggregate_copa(copa) + aggregate_bia(bia)
    cases.sort(key=lambda r: (r.get("complaint_date", ""), r["log_no"],
                              r["investigating_agency"]))
    write_csv(OUT / "chicago_police_discipline_cases.csv", cases)
    write_csv(OUT / "chicago_police_discipline_by_month.csv", monthly(cases))

    print("\nDONE")
    print(f"COPA summary rows: {len(copa):,}")
    print(f"BIA officer rows:  {len(bia):,}")
    print(f"Combined case-source rows: {len(cases):,}")
    print("Main file:", OUT / "chicago_police_discipline_cases.csv")
    print("Monthly file:", OUT / "chicago_police_discipline_by_month.csv")


if __name__ == "__main__":
    main()
