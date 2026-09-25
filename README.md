# Flock Cameras Research Project

This repository collects data and code for studying Flock Safety cameras, their locations, and related police complaints in Chicago. It also contains background research and a separate news dataset.

## What is here

| Folder | Contents |
| --- | --- |
| `scraper/` | Scripts for Chicago camera locations, OpenStreetMap/DeFlock cameras, and Flock news coverage. |
| `data/` | Collected camera, news, and COPA complaint data. |
| `bin/` | Research memos, a camera overview, and source notes. |
| `papers/` | Related papers and reading notes. |
| `logs/` | Dataset processing log. |

## Build the Chicago camera dataset

From the repository root, run:

```bash
python scraper/chicago_camera_deployment.py --out-dir data/chicago_camera_data
```

The script uses Python 3.9+ and its standard library. It downloads mapped cameras from OpenStreetMap via Overpass, then uses current geographic boundaries to add Chicago ZIP codes and police districts. It writes CSV files for the wider Chicago area, the city subset, and cameras explicitly tagged as Flock. It also saves the raw map response and run metadata. Run with `--help` for options such as `--refresh`, `--history`, and `--evidence`.

To add documented installation or operational dates, fill the generated `date_evidence_template.csv` with a date, source name, and URL for each camera, then rerun with `--evidence PATH_TO_FILE`.

## Other scripts

```bash
python scraper/deflock_camera_scraper.py --help
pip install -r scraper/requirements.txt
python scraper/flock_news_scraper.py --help
```

The first script collects mapped ALPR cameras in a chosen region. The news scraper collects articles and writes a structured dataset; its dependencies are listed in `scraper/requirements.txt`.

## Data limitations

- OpenStreetMap is crowdsourced. The mapped cameras are **not a complete inventory** of installed or operating Flock cameras.
- An OpenStreetMap edit date is **not** an installation or activation date. Camera dates require independent evidence tied to the device.
- ZIP codes and police districts come from current boundaries; they may not match historical assignments. A reverse geocoded street is approximate.
- The COPA files in `data/` are complaint records, not camera deployment records. Joining complaints to camera locations requires a separate research design.
