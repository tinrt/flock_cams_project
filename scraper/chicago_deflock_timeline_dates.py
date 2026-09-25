#!/usr/bin/env python3
"""
chicago_deflock_timeline_dates.py

Purpose
-------
Create a reproducible Chicago dataset for the date each CURRENTLY MAPPED
ALPR/ANPR camera first became an ALPR/ANPR object in OpenStreetMap.

Why this is the reliable interpretation of the DeFlock timeline
---------------------------------------------------------------
DeFlock's canonical camera record is OpenStreetMap (OSM). Its current camera
pipeline queries OSM/Overpass for:
    man_made=surveillance
    surveillance:type=ALPR
and the DeFlock timeline represents when cameras were reported/mapped, not a
verified physical installation date.

This script therefore does NOT scrape pixels/DOM from maps.deflock.org.
Instead it:
  1. Gets current ALPR/ANPR objects inside Chicago's official OSM boundary.
  2. Downloads each object's complete OSM API history.
  3. Finds the earliest historical version in which the object qualifies as
     an ALPR/ANPR camera.
  4. Saves that exact OSM timestamp, changeset, version, editor, and tags.
  5. Runs validation checks and preserves raw source files for auditability.

IMPORTANT
---------
`first_mapped_as_alpr_at` means first observable OSM/DeFlock map-report date.
It is NOT necessarily:
  - physical installation date
  - activation/operational date
  - purchase/contract date

Dependencies
------------
    pip install requests

Run from the repository root:
    python scraper/chicago_deflock_timeline_dates.py

Refresh current Chicago camera inventory:
    python scraper/chicago_deflock_timeline_dates.py --refresh-current

Force refresh of all OSM histories:
    python scraper/chicago_deflock_timeline_dates.py --refresh-current --refresh-history

Small test:
    python scraper/chicago_deflock_timeline_dates.py --limit 10

Outputs
-------
data/chicago_deflock_timeline_dates.csv
data/chicago_deflock_timeline_dates_metadata.json
data/chicago_deflock_timeline_dates_failures.csv       (only if failures)
data/chicago_deflock_timeline_dates_validation.csv     (only if warnings)
data/cache/deflock_timeline_chicago/...
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

OSM_API = "https://api.openstreetmap.org/api/0.6"

# Use Chicago's administrative relation rather than an arbitrary bbox.
CHICAGO_QUERY = r"""
[out:json][timeout:240];
area["name"="Illinois"]["boundary"="administrative"]["admin_level"="4"]->.illinois;
relation(area.illinois)
  ["name"="Chicago"]
  ["boundary"="administrative"]
  ["admin_level"="8"];
map_to_area->.chicago;

(
  nwr(area.chicago)
    ["man_made"="surveillance"]
    ["surveillance:type"~"^(ALPR|ANPR)$",i];
);
out center tags meta;
"""

USER_AGENT = (
    "flock-cams-project-chicago-timeline/2.0 "
    "(academic research; OSM history audit)"
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(x: Any) -> str:
    return str(x or "").strip().lower()


def qualifies_as_alpr(tags: Dict[str, str]) -> bool:
    return (
        norm(tags.get("man_made")) == "surveillance"
        and norm(tags.get("surveillance:type")) in {"alpr", "anpr"}
    )


def flock_evidence(tags: Dict[str, str]) -> Tuple[bool, str]:
    """
    Flag explicit current/historical Flock identification without assuming
    every ALPR camera is made by Flock.
    """
    for field in ("brand", "manufacturer", "operator", "model", "name", "description"):
        value = tags.get(field, "")
        if "flock" in norm(value):
            return True, f"{field}={value}"
    return False, ""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    attempts: int = 6,
    timeout: int = 120,
    **kwargs: Any,
) -> requests.Response:
    last_exc: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            r = session.request(method, url, timeout=timeout, **kwargs)

            if r.status_code == 200:
                return r

            if r.status_code in (429, 500, 502, 503, 504):
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = float(retry_after)
                else:
                    wait = min(60.0, 2 ** (attempt - 1) + random.random())

                print(
                    f"HTTP {r.status_code} from {url}; "
                    f"retry {attempt}/{attempts} in {wait:.1f}s"
                )
                time.sleep(wait)
                continue

            r.raise_for_status()

        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            wait = min(60.0, 2 ** (attempt - 1) + random.random())
            print(
                f"Request error {exc}; retry {attempt}/{attempts} "
                f"in {wait:.1f}s"
            )
            time.sleep(wait)

    raise RuntimeError(f"Request failed: {url}: {last_exc or 'HTTP failure'}")


def get_current_inventory(
    session: requests.Session,
    cache_file: Path,
    refresh: bool,
) -> Dict[str, Any]:
    if cache_file.exists() and not refresh:
        print(f"Using cached current inventory: {cache_file}")
        return json.loads(cache_file.read_text(encoding="utf-8"))

    errors: List[str] = []

    for endpoint in OVERPASS_ENDPOINTS:
        print(f"Querying Chicago cameras from {endpoint}")
        try:
            r = request_retry(
                session,
                "POST",
                endpoint,
                data={"data": CHICAGO_QUERY},
                attempts=3,
                timeout=300,
            )
            data = r.json()

            if not isinstance(data.get("elements"), list):
                raise RuntimeError("Overpass response has no elements list")

            # Refuse suspicious empty results rather than silently creating
            # a false zero-camera dataset.
            if len(data["elements"]) == 0:
                raise RuntimeError("Overpass returned zero Chicago cameras")

            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return data

        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
            print(f"  failed: {exc}")

    raise RuntimeError(
        "Every Overpass endpoint failed. No dataset was overwritten.\n"
        + "\n".join(errors)
    )


def history_path(cache_dir: Path, osm_type: str, osm_id: int) -> Path:
    return cache_dir / f"{osm_type}_{osm_id}.xml"


def get_history(
    session: requests.Session,
    osm_type: str,
    osm_id: int,
    cache_dir: Path,
    refresh: bool,
    delay: float,
) -> bytes:
    path = history_path(cache_dir, osm_type, osm_id)

    if path.exists() and not refresh:
        raw = path.read_bytes()
        # Verify cached XML before trusting it.
        try:
            ET.fromstring(raw)
            return raw
        except ET.ParseError:
            print(f"  cached XML corrupt; re-downloading {path.name}")

    url = f"{OSM_API}/{osm_type}/{osm_id}/history"
    r = request_retry(session, "GET", url, timeout=120)

    # Validate before writing cache.
    ET.fromstring(r.content)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(r.content)
    tmp.replace(path)

    if delay:
        time.sleep(delay)

    return r.content


def parse_history(raw: bytes, osm_type: str) -> Dict[str, Any]:
    root = ET.fromstring(raw)
    versions: List[Dict[str, Any]] = []

    for obj in root.findall(osm_type):
        tags = {
            t.attrib.get("k", ""): t.attrib.get("v", "")
            for t in obj.findall("tag")
        }

        versions.append(
            {
                "version": int(obj.attrib.get("version", "0")),
                "timestamp": obj.attrib.get("timestamp", ""),
                "changeset": obj.attrib.get("changeset", ""),
                "user": obj.attrib.get("user", ""),
                "uid": obj.attrib.get("uid", ""),
                "visible": obj.attrib.get("visible", "true").lower() != "false",
                "lat": obj.attrib.get("lat", ""),
                "lon": obj.attrib.get("lon", ""),
                "tags": tags,
            }
        )

    versions.sort(key=lambda x: x["version"])

    if not versions:
        raise RuntimeError("OSM history contains no versions")

    first_alpr = next(
        (
            v
            for v in versions
            if v["visible"] and qualifies_as_alpr(v["tags"])
        ),
        None,
    )

    if first_alpr is None:
        raise RuntimeError(
            "Current object is ALPR but no historical ALPR version was found"
        )

    previous = None
    for v in versions:
        if v["version"] < first_alpr["version"]:
            previous = v

    current = versions[-1]

    return {
        "object_created": versions[0],
        "first_alpr": first_alpr,
        "previous_before_alpr": previous,
        "latest_history_version": current,
        "version_count": len(versions),
    }


def current_coords(element: Dict[str, Any]) -> Tuple[Any, Any]:
    if element.get("type") == "node":
        return element.get("lat", ""), element.get("lon", "")
    center = element.get("center") or {}
    return center.get("lat", ""), center.get("lon", "")


def build_row(
    element: Dict[str, Any],
    history: Dict[str, Any],
    raw_history: bytes,
) -> Dict[str, Any]:
    osm_type = element["type"]
    osm_id = int(element["id"])
    current_tags = element.get("tags") or {}
    lat, lon = current_coords(element)

    first = history["first_alpr"]
    created = history["object_created"]
    previous = history["previous_before_alpr"]

    current_flock, current_flock_reason = flock_evidence(current_tags)
    first_flock, first_flock_reason = flock_evidence(first["tags"])

    return {
        # Stable identifiers
        "osm_type": osm_type,
        "osm_id": osm_id,
        "camera_key": f"{osm_type}/{osm_id}",

        # Current geography
        "latitude": lat,
        "longitude": lon,

        # Main research variable
        "first_mapped_as_alpr_at": first["timestamp"],
        "first_mapped_as_alpr_date": first["timestamp"][:10],
        "first_alpr_osm_version": first["version"],
        "first_alpr_changeset": first["changeset"],
        "first_alpr_osm_user": first["user"],
        "first_alpr_osm_uid": first["uid"],

        # Flock-specific evidence. Keep separate from ALPR membership.
        "currently_explicitly_flock": current_flock,
        "current_flock_evidence": current_flock_reason,
        "explicitly_flock_at_first_alpr_version": first_flock,
        "first_alpr_flock_evidence": first_flock_reason,

        # Distinguish object creation from ALPR appearance.
        "osm_object_created_at": created["timestamp"],
        "osm_object_created_date": created["timestamp"][:10],
        "osm_object_created_version": created["version"],
        "camera_tag_added_after_object_creation": first["version"] > created["version"],

        # What the object looked like immediately before becoming ALPR.
        "previous_version": previous["version"] if previous else "",
        "previous_timestamp": previous["timestamp"] if previous else "",
        "previous_was_alpr": (
            qualifies_as_alpr(previous["tags"]) if previous else False
        ),

        # Current OSM state from Overpass.
        "current_osm_version": element.get("version", ""),
        "current_osm_timestamp": element.get("timestamp", ""),
        "current_changeset": element.get("changeset", ""),
        "current_brand": current_tags.get("brand", ""),
        "current_manufacturer": current_tags.get("manufacturer", ""),
        "current_operator": current_tags.get("operator", ""),
        "current_model": current_tags.get("model", ""),
        "current_direction": current_tags.get("direction", ""),
        "current_surveillance_type": current_tags.get("surveillance:type", ""),

        # Audit/reproducibility fields
        "osm_history_version_count": history["version_count"],
        "history_sha256": sha256_bytes(raw_history),
        "osm_object_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "osm_history_api_url": f"{OSM_API}/{osm_type}/{osm_id}/history",
        "first_alpr_tags_json": json.dumps(
            first["tags"], ensure_ascii=False, sort_keys=True
        ),
        "current_tags_json": json.dumps(
            current_tags, ensure_ascii=False, sort_keys=True
        ),

        # Interpretation is explicit in every row.
        "date_interpretation": (
            "first observed OSM version tagged as ALPR/ANPR; "
            "not verified installation/activation date"
        ),
    }


def validate_row(row: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []

    first = row.get("first_mapped_as_alpr_at", "")
    created = row.get("osm_object_created_at", "")
    current = row.get("current_osm_timestamp", "")

    if not first:
        warnings.append("missing first_mapped_as_alpr_at")

    if created and first and created > first:
        warnings.append("object creation timestamp is after first ALPR timestamp")

    if first and current and first > current:
        warnings.append("first ALPR timestamp is after current Overpass timestamp")

    if not row.get("latitude") or not row.get("longitude"):
        warnings.append("missing current coordinates")

    return warnings


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        return

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(path)


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--output",
        default="data/chicago_deflock_timeline_dates.csv",
    )
    p.add_argument(
        "--cache-dir",
        default="data/cache/deflock_timeline_chicago",
    )
    p.add_argument("--refresh-current", action="store_true")
    p.add_argument("--refresh-history", action="store_true")
    p.add_argument("--delay", type=float, default=0.15)
    p.add_argument("--limit", type=int, default=0)
    return p.parse_args()


def main() -> int:
    a = args()

    output = Path(a.output)
    cache_dir = Path(a.cache_dir)
    inventory_cache = cache_dir / "current_chicago_alpr.json"
    history_dir = cache_dir / "osm_history"

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/xml, text/xml, */*",
        }
    )

    print("=" * 72)
    print("CHICAGO DEFLOCK / OSM FIRST-MAPPED CAMERA DATE")
    print("=" * 72)

    inventory = get_current_inventory(
        session,
        inventory_cache,
        a.refresh_current,
    )

    # De-duplicate defensively.
    elements: List[Dict[str, Any]] = []
    seen = set()

    for e in inventory["elements"]:
        key = (e.get("type"), e.get("id"))
        if key in seen:
            continue
        seen.add(key)
        elements.append(e)

    elements.sort(key=lambda e: (e["type"], int(e["id"])))

    if a.limit:
        elements = elements[: a.limit]

    print(f"\nCurrent Chicago ALPR/ANPR objects: {len(elements):,}")

    rows: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    validation: List[Dict[str, Any]] = []

    for i, e in enumerate(elements, 1):
        osm_type = e["type"]
        osm_id = int(e["id"])
        key = f"{osm_type}/{osm_id}"

        print(f"[{i:>4}/{len(elements)}] {key}", end="")

        try:
            raw = get_history(
                session,
                osm_type,
                osm_id,
                history_dir,
                a.refresh_history,
                a.delay,
            )
            parsed = parse_history(raw, osm_type)
            row = build_row(e, parsed, raw)
            rows.append(row)

            warnings = validate_row(row)
            for warning in warnings:
                validation.append(
                    {
                        "camera_key": key,
                        "warning": warning,
                    }
                )

            print(f" -> {row['first_mapped_as_alpr_date']}")

        except Exception as exc:
            print(f" -> FAILED: {exc}")
            failures.append(
                {
                    "osm_type": osm_type,
                    "osm_id": osm_id,
                    "camera_key": key,
                    "error": str(exc),
                }
            )

    # Never silently publish an obviously incomplete run.
    expected = len(elements)
    success_rate = len(rows) / expected if expected else 0

    if expected and success_rate < 0.95:
        print(
            f"\nERROR: only {len(rows)}/{expected} histories succeeded "
            f"({success_rate:.1%})."
        )
        print("Refusing to replace the main output with an incomplete dataset.")

        if failures:
            failure_path = output.with_name(
                output.stem + "_failures.csv"
            )
            write_csv(failure_path, failures)
            print(f"Failures saved to: {failure_path}")

        return 2

    rows.sort(
        key=lambda r: (
            r["first_mapped_as_alpr_at"],
            r["camera_key"],
        )
    )

    write_csv(output, rows)

    failure_path = output.with_name(output.stem + "_failures.csv")
    if failures:
        write_csv(failure_path, failures)
    elif failure_path.exists():
        failure_path.unlink()

    validation_path = output.with_name(output.stem + "_validation.csv")
    if validation:
        write_csv(validation_path, validation)
    elif validation_path.exists():
        validation_path.unlink()

    dates = [r["first_mapped_as_alpr_date"] for r in rows]
    flock_count = sum(bool(r["currently_explicitly_flock"]) for r in rows)

    metadata = {
        "generated_at_utc": now_utc(),
        "script_purpose": (
            "Reconstruct the first OSM/DeFlock map-report date of current "
            "Chicago ALPR/ANPR cameras."
        ),
        "geographic_scope": (
            "City of Chicago OSM administrative boundary, Illinois"
        ),
        "camera_filter": (
            "man_made=surveillance AND surveillance:type in {ALPR, ANPR}"
        ),
        "current_camera_count_requested": expected,
        "successful_history_count": len(rows),
        "failure_count": len(failures),
        "validation_warning_count": len(validation),
        "explicit_current_flock_tag_count": flock_count,
        "earliest_first_mapped_date": min(dates) if dates else None,
        "latest_first_mapped_date": max(dates) if dates else None,
        "main_variable": "first_mapped_as_alpr_at",
        "main_variable_definition": (
            "Earliest timestamp in the complete OSM element history where "
            "the object is visible and has man_made=surveillance plus "
            "surveillance:type=ALPR or ANPR."
        ),
        "critical_limitation": (
            "This measures when the camera was first mapped/reported in OSM, "
            "not its physical installation or operational date."
        ),
        "raw_inventory_cache": str(inventory_cache),
        "raw_history_cache": str(history_dir),
        "output_csv": str(output),
    }

    metadata_path = output.with_name(output.stem + "_metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 72)
    print("DONE")
    print("=" * 72)
    print(f"Dataset:       {output}")
    print(f"Metadata:      {metadata_path}")
    print(f"Rows:          {len(rows):,}")
    print(f"Failures:      {len(failures):,}")
    print(f"Warnings:      {len(validation):,}")
    print(f"Explicit Flock tags now: {flock_count:,}")
    if dates:
        print(f"Date range:    {min(dates)} -> {max(dates)}")

    print(
        "\nUse `first_mapped_as_alpr_date` as the DeFlock/OSM "
        "map-appearance date. Do not label it installation_date."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
