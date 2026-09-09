#!/usr/bin/env python3
"""
deflock_camera_scraper.py
=========================
Scrape ALPR (automated license plate reader) CAMERA LOCATION data for the
region shown on the DeFlock map (https://maps.deflock.org) and save it as CSV.

DeFlock's map is built on OpenStreetMap data: ALPR cameras are OSM nodes tagged
    man_made = surveillance
    surveillance:type = ALPR
so the reliable, structured source is the OSM Overpass API (the same data that
backs the DeFlock map). This script queries Overpass for a bounding box and
writes one row per camera.

Output columns:
    osm_id, lat, lon, operator, brand, manufacturer, direction,
    surveillance_type, surveillance_zone, name, ref, osm_url

Usage:
    python deflock_camera_scraper.py                       # default bbox (NE/Mid-Atlantic)
    python deflock_camera_scraper.py --south 40 --west -75.5 --north 41.5 --east -72.5
    python deflock_camera_scraper.py --out ../data/deflock_alpr_cameras.csv

Notes:
    * Needs open internet access to https://overpass-api.de (a public API).
    * The default bounding box matches the DeFlock map view
      lat=39.0479, lng=-73.8505, zoom=6.54 (Northeast / Mid-Atlantic US).
    * Be polite: Overpass is a shared free service. Don't hammer it.
"""
from __future__ import annotations
import argparse, csv, sys, time
import urllib.request, urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FIELDS = ["osm_id", "lat", "lon", "operator", "brand", "manufacturer",
          "direction", "surveillance_type", "surveillance_zone", "name", "ref", "osm_url"]

def build_query(s, w, n, e):
    # out:csv keeps the payload compact; ~i makes the ALPR match case-insensitive
    cols = '::id,::lat,::lon,operator,brand,manufacturer,direction,"surveillance:type","surveillance:zone",name,ref'
    return (f'[out:csv({cols};true;",")][timeout:180];'
            f'node["man_made"="surveillance"]["surveillance:type"~"ALPR",i]'
            f'({s},{w},{n},{e});out;')

def fetch(query, retries=3):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                OVERPASS_URL, data=data,
                headers={"User-Agent": "flock_cams-research/1.0 (academic; OSM Overpass)"})
            with urllib.request.urlopen(req, timeout=200) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as ex:  # noqa
            last = ex
            wait = 5 * attempt
            print(f"  attempt {attempt} failed ({ex}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(f"Overpass request failed after {retries} attempts: {last}")

def parse_and_write(raw, out_path):
    lines = raw.splitlines()
    if not lines:
        raise SystemExit("empty Overpass response")
    rows = list(csv.reader(lines))
    header, body = rows[0], rows[1:]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in body:
            r = (r + [""] * 11)[:11]
            osm_id = r[0]
            w.writerow(r + [f"https://www.openstreetmap.org/node/{osm_id}"])
    return len(body)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Scrape DeFlock/OSM ALPR camera locations to CSV.")
    ap.add_argument("--south", type=float, default=36.0)
    ap.add_argument("--west",  type=float, default=-80.0)
    ap.add_argument("--north", type=float, default=43.5)
    ap.add_argument("--east",  type=float, default=-70.0)
    ap.add_argument("--out", default="../data/deflock_alpr_cameras.csv")
    a = ap.parse_args(argv)
    print(f"Querying Overpass for ALPR cameras in bbox "
          f"S={a.south} W={a.west} N={a.north} E={a.east} ...", file=sys.stderr)
    raw = fetch(build_query(a.south, a.west, a.north, a.east))
    count = parse_and_write(raw, a.out)
    print(f"Wrote {count} cameras to {a.out}")

if __name__ == "__main__":
    main()
