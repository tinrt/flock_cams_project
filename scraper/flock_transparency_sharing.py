#!/usr/bin/env python3
"""
flock_transparency_sharing.py

Reliable Flock sharing collector.

Instead of scraping transparency.flocksafety.com directly (Cloudflare blocks
plain requests), this downloads the public EyesOnFlock-derived sharing network
published by the DeFlock data project.

Sources:
  https://deflockdata.dontgetflocked.com/sharing-network-nodes.geojson
  https://deflockdata.dontgetflocked.com/sharing-network-adjacency.json
  https://deflockdata.dontgetflocked.com/sharing-network-meta.json

Outputs:
  data/flock_sharing/flock_portals.csv
  data/flock_sharing/flock_sharing_edges.csv
  data/flock_sharing/chicago_access_edges.csv
  data/flock_sharing/chicago_summary.csv
  data/flock_sharing/source_metadata.json

Run:
  python scraper/flock_transparency_sharing.py

Optional agency search:
  python scraper/flock_transparency_sharing.py --agency "Chicago"
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

BASE = "https://deflockdata.dontgetflocked.com"
NODES_URL = f"{BASE}/sharing-network-nodes.geojson"
ADJ_URL = f"{BASE}/sharing-network-adjacency.json"
META_URL = f"{BASE}/sharing-network-meta.json"

OUT = Path("data/flock_sharing")
RAW = OUT / "raw"

HEADERS = {
    "User-Agent": "flock-cams-project academic research/3.0",
    "Accept": "application/json, application/geo+json",
}


def get_json(url: str) -> Any:
    r = requests.get(url, headers=HEADERS, timeout=180)
    r.raise_for_status()
    return r.json()


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def prop(p: Dict[str, Any], *names: str, default: Any = "") -> Any:
    for n in names:
        if n in p and p[n] not in (None, ""):
            return p[n]
    return default


def norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def is_chicago(name: str, state: str = "") -> bool:
    n = norm(name)
    s = norm(state)
    return (
        n in {"chicago il pd", "chicago police department", "chicago pd"}
        or ("chicago" in n and (" pd" in f" {n}" or "police" in n))
    ) and (not s or s in {"il", "illinois"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--agency",
        default="Chicago",
        help="Text to search agency names after download (default: Chicago)",
    )
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    print("Downloading current public sharing-network data...")
    nodes = get_json(NODES_URL)
    adjacency = get_json(ADJ_URL)
    meta = get_json(META_URL)

    # Preserve exact source snapshots used in this run.
    (RAW / "sharing-network-nodes.geojson").write_text(
        json.dumps(nodes, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "sharing-network-adjacency.json").write_text(
        json.dumps(adjacency, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "source_metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    features = nodes.get("features", [])
    if not features:
        raise RuntimeError("Source returned zero agency nodes.")

    # Build slug -> agency information.
    agencies: Dict[str, Dict[str, Any]] = {}

    for f in features:
        p = f.get("properties") or {}
        slug = str(prop(p, "portalSlug", "portal_slug", "slug", "id"))
        if not slug:
            continue

        coords = (f.get("geometry") or {}).get("coordinates") or ["", ""]
        lon = coords[0] if len(coords) > 0 else ""
        lat = coords[1] if len(coords) > 1 else ""

        agencies[slug] = {
            "slug": slug,
            "agency": str(prop(
                p, "name", "agency", "organizationName", "organization", "displayName",
                default=slug
            )),
            "state": str(prop(p, "state", "stateAbbr", "stateCode")),
            "city": str(prop(p, "city", "place", "jurisdiction")),
            "is_portal": prop(p, "isPortal", "is_portal", default=False),
            "portal_url": (
                f"https://transparency.flocksafety.com/{slug}"
                if prop(p, "isPortal", "is_portal", default=False)
                else ""
            ),
            "connection_count": prop(p, "connectionCount", "connection_count"),
            "latitude": lat,
            "longitude": lon,
        }

    # Portal table.
    portals = [
        a for a in agencies.values()
        if str(a["is_portal"]).lower() in {"true", "1"}
    ]
    portals.sort(key=lambda x: (x["state"], x["agency"]))

    write_csv(
        OUT / "flock_portals.csv",
        portals,
        [
            "slug", "agency", "city", "state", "is_portal",
            "portal_url", "connection_count", "latitude", "longitude"
        ],
    )

    # Adjacency is directional:
    # portal owner slug -> organizations granted access to owner's data.
    edges: List[Dict[str, Any]] = []

    for owner_slug, targets in adjacency.items():
        owner = agencies.get(owner_slug, {
            "agency": owner_slug, "state": "", "city": "", "portal_url": ""
        })

        if not isinstance(targets, list):
            continue

        for target_slug in targets:
            target = agencies.get(str(target_slug), {
                "agency": str(target_slug), "state": "", "city": "", "portal_url": ""
            })

            edges.append({
                "data_owner_slug": owner_slug,
                "data_owner_agency": owner["agency"],
                "data_owner_city": owner.get("city", ""),
                "data_owner_state": owner.get("state", ""),
                "agency_with_access_slug": target_slug,
                "agency_with_access": target["agency"],
                "agency_with_access_city": target.get("city", ""),
                "agency_with_access_state": target.get("state", ""),
                "relationship": "owner_grants_access_to_agency",
                "owner_portal_url": owner.get("portal_url", ""),
                "source": "EyesOnFlock transparency-portal snapshot",
                "source_generated_at": prop(
                    meta, "generatedAt", "generated_at", "generated_at_utc"
                ),
            })

    if not edges:
        raise RuntimeError(
            "Source returned zero sharing edges; refusing to write an empty result."
        )

    edges.sort(key=lambda x: (x["data_owner_agency"], x["agency_with_access"]))

    edge_fields = [
        "data_owner_slug", "data_owner_agency", "data_owner_city",
        "data_owner_state", "agency_with_access_slug", "agency_with_access",
        "agency_with_access_city", "agency_with_access_state", "relationship",
        "owner_portal_url", "source", "source_generated_at"
    ]

    write_csv(OUT / "flock_sharing_edges.csv", edges, edge_fields)

    # Chicago on either side of the relationship.
    chicago_edges = [
        e for e in edges
        if is_chicago(e["data_owner_agency"], e["data_owner_state"])
        or is_chicago(e["agency_with_access"], e["agency_with_access_state"])
    ]
    write_csv(OUT / "chicago_access_edges.csv", chicago_edges, edge_fields)

    # Easy-to-read Chicago summary.
    summary = []
    for e in chicago_edges:
        if is_chicago(e["data_owner_agency"], e["data_owner_state"]):
            summary.append({
                "direction": "Chicago shares its data with",
                "other_agency": e["agency_with_access"],
                "other_city": e["agency_with_access_city"],
                "other_state": e["agency_with_access_state"],
                "evidence_portal": e["owner_portal_url"],
            })
        if is_chicago(e["agency_with_access"], e["agency_with_access_state"]):
            summary.append({
                "direction": "Chicago can access data from",
                "other_agency": e["data_owner_agency"],
                "other_city": e["data_owner_city"],
                "other_state": e["data_owner_state"],
                "evidence_portal": e["owner_portal_url"],
            })

    write_csv(
        OUT / "chicago_summary.csv",
        summary,
        ["direction", "other_agency", "other_city", "other_state", "evidence_portal"],
    )

    # User-requested search preview.
    q = norm(args.agency)
    matches = [
        a for a in agencies.values()
        if q and q in norm(a["agency"])
    ]

    print("\nDONE")
    print(f"Agency nodes:       {len(agencies):,}")
    print(f"Public portals:     {len(portals):,}")
    print(f"Directed edges:     {len(edges):,}")
    print(f"Chicago edges:      {len(chicago_edges):,}")
    print(f"'{args.agency}' agency matches: {len(matches):,}")

    for a in matches[:20]:
        print(f"  - {a['agency']} ({a['state']}) [{a['slug']}]")

    print("\nOutputs:")
    print(" ", OUT / "flock_portals.csv")
    print(" ", OUT / "flock_sharing_edges.csv")
    print(" ", OUT / "chicago_access_edges.csv")
    print(" ", OUT / "chicago_summary.csv")
    print(" ", OUT / "source_metadata.json")

    if not chicago_edges:
        print(
            "\nWARNING: the current source snapshot contains no relationship "
            "matched to Chicago. The full network was still exported; inspect "
            "agency names with --agency Chicago."
        )


if __name__ == "__main__":
    main()
