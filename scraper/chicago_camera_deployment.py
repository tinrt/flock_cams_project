#!/usr/bin/env python3
"""Create a Chicago ALPR/Flock camera inventory with explicitly sourced dates.

Data: OSM/DeFlock via Overpass; City of Chicago ZIP and current police-district
polygons. Python 3.9+ standard library only. OSM is a crowdsourced inventory:
an unrecorded camera is not necessarily absent. No date is inferred from OSM
edit timestamps. Optional evidence CSV can supply independently checked dates.

Run: python chicago_camera_deployment.py --out-dir chicago_data
     python chicago_camera_deployment.py --out-dir chicago_data --evidence installation_evidence.csv

Outputs: chicago_area_all_cameras.csv; chicago_city_cameras.csv;
         chicago_city_flock_cameras.csv; raw_overpass.json; date_evidence_template.csv;
         run_metadata.json; cached polygons and OSM history files.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS = "https://overpass-api.de/api/interpreter"
# The city's fthy-xz3r export currently returns a truncated (invalid) GeoJSON.
# This CPD district map layer is a usable polygon fallback; source is recorded.
DISTRICTS = "https://services7.arcgis.com/8kZv9DESIQ1hYuyJ/arcgis/rest/services/District_24_links_WFL1/FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson"
ZIPS = "https://data.cityofchicago.org/api/geospatial/unjd-c2ca?method=export&format=GeoJSON"
OSM_HISTORY = "https://api.openstreetmap.org/api/0.6/node/{id}/history.json"
CITY_REVERSE = "https://gisapps.chicago.gov/arcgis/rest/services/GeoStreets/GeocodeServer/reverseGeocode"
# A candidate region only. Membership is decided by the police district polygons.
BBOX = (41.63, -87.95, 42.03, -87.51)
USER_AGENT = "ChicagoCameraDeploymentResearch/1.0 (OSM and public GIS data; contact: research@example.org)"
FIELDS = [
    "osm_type", "osm_id", "osm_url", "latitude", "longitude", "manufacturer", "brand", "model",
    "operator", "camera_class", "name", "in_chicago_city", "address", "address_source", "zip_code",
    "zip_source", "police_district", "district_source", "direction", "surveillance_type",
    "last_osm_edit_utc", "osm_version", "osm_changeset_id", "osm_changeset_url", "osm_last_editor", "osm_last_editor_uid", "first_osm_mapped_utc", "first_alpr_tagged_utc",
    "first_flock_tagged_utc", "history_status", "installation_date", "installation_date_source",
    "installation_date_url", "operational_date", "operational_date_source",
    "operational_date_url", "date_notes", "osm_start_date_tag", "osm_construction_date_tag",
    "osm_opening_date_tag", "osm_tags_json", "osm_full_element_json",
]
EVIDENCE_FIELDS = [
    "osm_id", "installation_date", "installation_date_source", "installation_date_url",
    "operational_date", "operational_date_source", "operational_date_url", "date_notes",
]


def get_bytes(url: str, data: bytes | None = None, attempts: int = 3) -> bytes:
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Could not retrieve {url}: {last}")


def get_json(url: str, **kw):
    return json.loads(get_bytes(url, **kw))


def load_cached_json(path: Path, url: str, refresh: bool = False):
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    payload = get_json(url)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def fetch_overpass(out: Path, refresh: bool):
    path = out / "raw_overpass.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    s, w, n, e = BBOX
    # Include all nodes and ways marked as ALPR, plus any other mapped Flock
    # surveillance devices. Confirm brand separately, preserving unknowns.
    query = (f'[out:json][timeout:180];('
             f'nwr["surveillance:type"~"ALPR|ANPR|license.?plate",i]({s},{w},{n},{e});'
             f'nwr["man_made"="surveillance"]["manufacturer"~"flock",i]({s},{w},{n},{e});'
             f'nwr["man_made"="surveillance"]["brand"~"flock",i]({s},{w},{n},{e});'
             f');out center meta;')
    data = get_json(OVERPASS, data=urllib.parse.urlencode({"data": query}).encode())
    if "elements" not in data:
        raise RuntimeError(f"Unexpected Overpass response: {str(data)[:300]}")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def in_ring(x, y, ring):
    inside = False
    px, py = ring[-1]
    for qx, qy in ring:
        # Boundary points belong to both polygons: flag conflicts later.
        cross = (x - px) * (qy - py) - (y - py) * (qx - px)
        if abs(cross) < 1e-10 and min(px, qx) - 1e-10 <= x <= max(px, qx) + 1e-10 and min(py, qy) - 1e-10 <= y <= max(py, qy) + 1e-10:
            return True
        if (qy > y) != (py > y) and x < (px - qx) * (y - qy) / (py - qy) + qx:
            inside = not inside
        px, py = qx, qy
    return inside


def in_geometry(lon, lat, geometry):
    if not geometry:
        return False
    typ = geometry.get("type")
    if typ == "Polygon":
        polygons = [geometry["coordinates"]]
    elif typ == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        return False
    return any(in_ring(lon, lat, p[0]) and not any(in_ring(lon, lat, h) for h in p[1:]) for p in polygons if p)


def lookup(lon, lat, features, keys):
    matched = []
    for feature in features:
        if in_geometry(lon, lat, feature.get("geometry")):
            properties = feature.get("properties") or {}
            value = next((str(properties[k]) for k in keys if properties.get(k) is not None), "")
            matched.append(value)
    # Empty or ambiguous geographic join is explicit rather than an invented assignment.
    return matched[0] if len(matched) == 1 else "", len(matched)


def classify(tags):
    maker = " ".join(str(tags.get(k, "")) for k in ("manufacturer", "brand", "model"))
    if re.search(r"\bflock(?:\s+safety)?\b", maker, re.I):
        return "flock_confirmed_by_osm_tag"
    if maker.strip():
        return "other_or_unverified_manufacturer"
    return "manufacturer_unknown"


def address(tags):
    full = tags.get("addr:full", "").strip()
    if full:
        return full, "OSM addr:full"
    street = tags.get("addr:street", "").strip()
    if street:
        return " ".join(filter(None, [tags.get("addr:housenumber", "").strip(), street])), "OSM address tags"
    # A corner or road hint is not a postal/street address.
    return "", "not available in OSM"


def city_reverse_address(osm_type, osm_id, lat, lon, out, delay):
    """Optional nearest street address: approximate, never a verified camera address."""
    path = out / "address_lookup" / f"{osm_type}_{osm_id}.json"
    try:
        if not path.exists():
            time.sleep(delay)
        query = urllib.parse.urlencode({"location": f"{lon},{lat}", "distance": "100", "outSR": "4326", "f": "json"})
        payload = load_cached_json(path, CITY_REVERSE + "?" + query)
        if payload.get("error"):
            return "", "city geocoder returned an error"
        label = (payload.get("address") or {}).get("Match_addr", "")
        return label, "approximate nearest Chicago street from city reverse geocoder" if label else "city geocoder had no match"
    except Exception as exc:
        print(f"Address lookup unavailable for {osm_type}/{osm_id}: {exc}", file=sys.stderr)
        return "", "city geocoder unavailable"


def iso_date(value, label):
    value = (value or "").strip()
    if value:
        try:
            dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be YYYY-MM-DD, got {value!r}") from exc
    return value


def evidence_map(path: Path | None):
    if not path:
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(EVIDENCE_FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Evidence CSV missing fields: {sorted(missing)}")
        output = {}
        for entry in reader:
            key = str(entry["osm_id"]).strip().removeprefix("node/")
            if not key or key in output:
                raise ValueError(f"Evidence osm_id missing or repeated: {key!r}")
            for field in ("installation", "operational"):
                date = iso_date(entry[f"{field}_date"], field)
                if date and (not entry[f"{field}_date_source"].strip() or not entry[f"{field}_date_url"].strip()):
                    raise ValueError(f"{key}: {field} date needs source name and source URL")
                entry[f"{field}_date"] = date
            output[key] = entry
    return output


def history_dates(node_id, out, refresh, delay):
    osm_type, osm_id = node_id.split("/", 1)
    path = out / "osm_history" / f"{osm_type}_{osm_id}.json"
    try:
        if not path.exists() or refresh:
            time.sleep(delay)
        payload = load_cached_json(path, f"https://api.openstreetmap.org/api/0.6/{osm_type}/{osm_id}/history.json", refresh)
        elements = sorted(payload.get("elements", []), key=lambda e: e.get("timestamp", ""))
        def first(predicate):
            return next((v.get("timestamp", "") for v in elements if predicate(v.get("tags") or {})), "")
        return (first(lambda _: True),
                first(lambda t: "alpr" in t.get("surveillance:type", "").lower()),
                first(lambda t: classify(t) == "flock_confirmed_by_osm_tag"), "ok")
    except Exception as exc:
        print(f"History unavailable for node {node_id}: {exc}", file=sys.stderr)
        return "", "", "", f"error: {type(exc).__name__}"


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", type=Path, default=Path("chicago_camera_data"))
    parser.add_argument("--evidence", type=Path, help="Curated date evidence keyed by OSM node ID")
    parser.add_argument("--refresh", action="store_true", help="Redownload Overpass, polygons and OSM histories")
    parser.add_argument("--skip-history", action="store_true", help="Deprecated alias: skip OSM history requests (the default)")
    parser.add_argument("--history", action="store_true", help="Fetch OSM edit histories for city Flock-tagged cameras")
    parser.add_argument("--history-all", action="store_true", help="Fetch per-object OSM histories for every area camera (can take a long time)")
    parser.add_argument("--history-delay", type=float, default=1.0, help="Seconds between uncached OSM history calls")
    parser.add_argument("--lookup-addresses", action="store_true", help="Try Chicago reverse geocoder for missing city Flock addresses")
    parser.add_argument("--lookup-all-city-addresses", action="store_true", help="Try reverse geocoder for all missing city camera addresses (many calls)")
    args = parser.parse_args(argv)
    if args.history_delay < 0:
        parser.error("--history-delay cannot be negative")
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "osm_history").mkdir(exist_ok=True)
    (out / "address_lookup").mkdir(exist_ok=True)
    districts = load_cached_json(out / "district_boundaries.geojson", DISTRICTS, args.refresh)["features"]
    zips = load_cached_json(out / "zip_boundaries.geojson", ZIPS, args.refresh)["features"]
    if not any(f.get("geometry") for f in districts) or not any(f.get("geometry") for f in zips):
        raise RuntimeError("Boundary data missing geometry; check downloaded GIS source")
    elements = fetch_overpass(out, args.refresh)["elements"]
    evidence = evidence_map(args.evidence)
    results = []
    for element in elements:
        if element.get("type") not in ("node", "way", "relation"):
            continue
        position = element if "lat" in element and "lon" in element else element.get("center", {})
        if "lat" not in position or "lon" not in position:
            continue
        lat, lon = float(position["lat"]), float(position["lon"])
        district, count = lookup(lon, lat, districts, ("dist_num", "district", "dist", "DIST_NUM", "DISTRICT"))
        zip_code, zip_count = lookup(lon, lat, zips, ("zip", "ZIP", "zip_code"))
        tags = element.get("tags") or {}
        osm_id = str(element["id"])
        osm_type = element["type"]
        addr, addr_source = address(tags)
        if not addr and count > 0 and (args.lookup_all_city_addresses or (args.lookup_addresses and classify(tags) == "flock_confirmed_by_osm_tag")):
            addr, addr_source = city_reverse_address(osm_type, osm_id, lat, lon, out, max(0.25, args.history_delay))
        first_mapped = first_alpr = first_flock = ""
        history_status = "skipped"
        if not args.skip_history and (args.history_all or (args.history and count > 0 and classify(tags) == "flock_confirmed_by_osm_tag")):
            first_mapped, first_alpr, first_flock, history_status = history_dates(f"{osm_type}/{osm_id}", out, args.refresh, args.history_delay)
        ev = evidence.get(osm_id, {})
        # Explicit opening/start tags are candidate evidence only, requiring review.
        row = {
            "osm_type": osm_type, "osm_id": osm_id, "osm_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
            "latitude": lat, "longitude": lon,
            "manufacturer": tags.get("manufacturer", ""), "brand": tags.get("brand", ""),
            "model": tags.get("model", ""), "operator": tags.get("operator", ""),
            "camera_class": classify(tags), "name": tags.get("name", ""),
            "in_chicago_city": "yes" if count else "no (or not matched to district polygons)",
            "address": addr, "address_source": addr_source,
            "zip_code": zip_code or tags.get("addr:postcode", ""),
            "zip_source": ("Chicago ZIP polygon" if zip_code else "OSM addr:postcode" if tags.get("addr:postcode") else "unresolved"),
            "police_district": district, "district_source": "Chicago current district polygon" if district else f"ambiguous polygon matches ({count})",
            "direction": tags.get("direction", ""), "surveillance_type": tags.get("surveillance:type", ""),
            "last_osm_edit_utc": element.get("timestamp", ""),
            "osm_version": element.get("version", ""),
            "osm_changeset_id": element.get("changeset", ""),
            "osm_changeset_url": f"https://www.openstreetmap.org/changeset/{element['changeset']}" if element.get("changeset") else "",
            "osm_last_editor": element.get("user", ""),
            "osm_last_editor_uid": element.get("uid", ""),
            "first_osm_mapped_utc": first_mapped, "first_alpr_tagged_utc": first_alpr,
            "first_flock_tagged_utc": first_flock, "history_status": history_status,
            "osm_start_date_tag": tags.get("start_date", ""),
            "osm_construction_date_tag": tags.get("construction_date", ""),
            "osm_opening_date_tag": tags.get("opening_date", ""),
            "osm_tags_json": json.dumps(tags, ensure_ascii=False, sort_keys=True),
            "osm_full_element_json": json.dumps(element, ensure_ascii=False, sort_keys=True),
        }
        for field in EVIDENCE_FIELDS[1:]:
            row[field] = ev.get(field, "")
        if zip_count > 1:
            print(f"ZIP overlap for OSM node {osm_id}: {zip_count} polygons", file=sys.stderr)
        results.append(row)
    results.sort(key=lambda r: (r["osm_type"], int(r["osm_id"])))
    if not results:
        print("No mapped ALPR/Flock nodes found; outputs have headers only. Check source coverage.", file=sys.stderr)
    city = [r for r in results if r["in_chicago_city"] == "yes"]
    flock = [r for r in city if r["camera_class"] == "flock_confirmed_by_osm_tag"]
    write_csv(out / "chicago_area_all_cameras.csv", results, FIELDS)
    write_csv(out / "chicago_city_cameras.csv", city, FIELDS)
    write_csv(out / "chicago_city_flock_cameras.csv", flock, FIELDS)
    template = out / "date_evidence_template.csv"
    if not template.exists():
        write_csv(template, [{field: r["osm_id"] if field == "osm_id" else "" for field in EVIDENCE_FIELDS} for r in city], EVIDENCE_FIELDS)
    metadata = {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "all_area_mapped_camera_count": len(results),
        "chicago_city_mapped_camera_count": len(city), "chicago_city_confirmed_flock_count": len(flock),
        "missing_zip_count": sum(not r["zip_code"] for r in results),
        "missing_address_count": sum(not r["address"] for r in results),
        "verified_installation_dates": sum(bool(r["installation_date"]) for r in results),
        "verified_operational_dates": sum(bool(r["operational_date"]) for r in results),
        "sources": {"overpass": OVERPASS, "districts": DISTRICTS, "zips": ZIPS, "osm_history": OSM_HISTORY},
        "notes": ["OSM map/edit dates are observations, not installation or activation dates.",
                  "Dates require independently documented, camera-matched evidence.",
                  "Address stays blank when OSM has no address; optional city reverse geocoder returns only approximate nearest street.",
                  "District polygons are current, not historical boundaries.",
                  "Area output contains suburbs in a fixed bounding box; city output uses district boundary polygons.",
                  "This is a mapped-camera sample, not a census of every installed Flock camera."],
    }
    (out / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in metadata.items() if k.endswith("count") or k.endswith("dates")}, indent=2))


if __name__ == "__main__":
    main()
