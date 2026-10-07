# ALPR / Flock Camera Research Project

## Overview

This project collects data on **Automated License Plate Reader (ALPR)** adoption by U.S. police departments, with Chicago as the current main case.

The project addresses six questions:

1. Where are ALPR cameras located?
2. When did police departments begin using ALPRs?
3. What police misconduct/disciplinary data are available?
4. Which police departments can access other agencies' Flock data?
5. What are each agency's monthly reported offenses, clearances, and arrests?
6. What prior technology experience can be documented as a proxy for absorptive capacity?

---

## Data Collection

### 1. ALPR Camera Locations

Camera-level information is collected primarily from **DeFlock and OpenStreetMap (OSM)**.

For Chicago cameras, we collect available information such as:

- Coordinates
- Address and ZIP code
- Police district
- Camera/operator information
- OSM record and edit information

OSM history is also used to determine when a camera **first appeared as an ALPR camera in the map data**.

**Limitation:** first mapped date is not necessarily the physical installation or operational date.

---

### 2. Police Department ALPR Adoption Dates

Because camera-level installation dates are often unavailable, we use the **Atlas of Surveillance** to identify when police departments began using ALPR technology.

The script searches Atlas descriptions for evidence such as:

> “The department has used ALPRs since 2015.”

Dates are classified as:

- `first_use`
- `installation`
- `deployment`
- `purchase`
- `contract/approval`
- `known_by`

The original sentence supporting each date is retained for verification.

**Outputs:**

`atlas_alpr_agency_launch_dates.csv` — Main agency-level adoption dataset.

`atlas_alpr_agency_launch_dates_manual_review.csv` — Agencies where the adoption date is missing or uncertain.

A purchase or contract date is **not automatically treated as the operational start date**.

---

### 3. Chicago Police Misconduct and Discipline

We initially collected **COPA (Civilian Office of Police Accountability)** complaint data.

We expanded this to include **BIA (Bureau of Internal Affairs)** because COPA alone does not cover all Chicago police misconduct investigations.

The collector downloads COPA summary, BIA involved-officer, and optional COPA involved-officer records. The current combined output uses COPA summaries and aggregated BIA records; COPA officer records are supplementary.

The source files support investigation of:

- Complaints
- Misconduct categories
- Investigation findings
- Disciplinary outcomes, when available

**Outputs:**

`chicago_police_discipline_cases.csv` — Case-level data.

`chicago_police_discipline_by_month.csv` — Monthly aggregated source-record counts.

**Under validation:** COPA and BIA records may overlap. The combined file is not yet a deduplicated complaint panel, and the current findings mapping does not capture the raw `finding_code` field. These outputs require further preparation before analysis.

---

### 4. Flock Data Sharing Across Agencies

Owning Flock cameras and having access to Flock data are not necessarily the same.

For example:

Agency A owns cameras and grants Agency B access to its data.

Therefore, an agency without its own cameras may still be exposed to Flock.

We collect public agency-to-agency sharing relationships derived from **Flock Transparency Portal** information.

**Outputs:**

`flock_sharing_edges.csv` — Full sharing network.

`chicago_access_edges.csv` — Relationships involving Chicago.

`chicago_summary.csv` — Simplified Chicago sharing information.

**Limitation:** we can identify sharing relationships, but we do not yet have reliable historical dates for when each relationship began.

---

### 5. FBI Monthly Offenses, Clearances, and Arrests

Added October 6, 2026. The collector retrieves agency-level FBI Crime Data Explorer data, starting with **Illinois, January 2021–December 2025**. Agency names and ORI codes are downloaded automatically.

Each successful agency/offense request produces a 60-month panel, preserving missing values and reported zeros.

- **Offenses and clearances:** motor vehicle theft, larceny/theft, robbery, burglary, aggravated assault, homicide, and arson.
- **Optional arrests:** those seven categories, plus stolen property, vandalism, weapons violations, and DUI.

Clearances count offenses solved by arrest or exceptional means. Arrest counts are a separate outcome. The API uses different code systems: motor vehicle theft is NIBRS `240`, summary `MVT`, and arrest `90`. Theft from vehicles (`23F`) and vehicle parts (`23G`) cannot be separated from broader larceny in this summary endpoint.

**Main outputs in `data/fbi_clearances/`:**

- `clearances_monthly.csv` — Agency × offense × month, with offense counts, clearances, and clearance ratios.
- `arrests_monthly.csv` — Optional agency × arrest category × month.
- `agency_directory.csv` — Names, ORIs, and agency metadata.
- `coverage_by_agency_offense.csv` — Available, partial, and missing months after a completed run.
- `request_manifest.csv`, `run_metadata.json`, and `raw/` — Download audit and cached responses; final run metadata is written on completion.

**Limitations:** monthly clearances can concern crimes reported earlier, so clearance ratios are not cohort probabilities and can exceed 100%. Reporting transitions and agency coverage require review, particularly early 2021. These data do not identify whether cameras helped solve an offense.

### 6. Full Atlas Data and Absorptive-Capacity Proxy

Added October 6, 2026. Downloaded the **full official Atlas of Surveillance export**, containing **15,135 records across 13 source technology labels**. The original ALPR-only export is retained.

The script creates:

`atlas_based_absorptive_capacity = number of distinct technology types with qualifying agency adoption/use evidence`

It searches summary sentences for technology phrases, acronyms, and product names, then checks for adoption or use language, such as “uses,” “operates,” “installed,” or “began a program.”

- Counts each technology family once per agency.
- Excludes Flock-linked evidence so the treatment does not mechanically increase the index.
- Excludes plans, grants alone, contract approvals, negation, and free trials.
- Keeps completed purchases in a separate procurement-inclusive sensitivity index.
- Retains original sentences, matched keywords, source links, dates, and decisions for review.
- Flags uncertain agency attribution and candidate ORI collisions rather than silently merging distinct agencies.

Recognised families include ALPR, gunshot detection, body-worn cameras, drones, facial recognition, real-time crime centers, predictive policing, camera networks and registries, cell-site simulators, mobile-device forensics, investigative platforms, video analytics, and fusion centers.

**Source:** `data/atlas_full/atlas_full.csv`, with retrieval metadata and checksum.

**Outputs in `data/atlas_absorptive_capacity/`:**

- `atlas_based_absorptive_capacity.csv` — Agency scores, technology indicators, and identity/coverage flags.
- `adoption_evidence_audit.csv` — Accepted and excluded technology evidence.
- `excluded_and_review_evidence.csv` — Evidence requiring review or excluded by the rules.
- `technology_dictionary.csv` and `run_metadata.json` — Matching rules and run summary.

A separate pre-2021 output is available in `data/atlas_absorptive_capacity_pre2021/`, using only qualifying evidence explicitly dated by 2020.

**Limitations:** this is a proposed proxy for documented technology experience, not a validated direct measure of absorptive capacity. Zero means no qualifying evidence in the supplied records. Default scores are snapshots; pre-treatment measurement requires verified timing. Automated sentence classifications and agency matches need review.

---

# Setup

## 1. Clone the repository

```bash
git clone https://github.com/tinrt/flock_cams_project.git
cd flock_cams_project
```

## 2. Install Python packages

Python 3.10 or newer is recommended for the project. The new FBI and Atlas-index scripts use only the Python standard library and need no additional packages.

```bash
pip install pandas requests beautifulsoup4
```

If a script reports a missing package, install it with:

```bash
pip install package_name
```

## 3. Update an existing local copy

Before running the pipeline:

```bash
git pull origin main
```

---

# Running the Pipeline

Scripts should be run from the **project root directory**.

## Step 1 — Collect / update Chicago camera data

Run the Chicago camera collection scripts in the `scraper/` folder.

These collect camera locations and available OSM information.

The resulting data are stored under:

```text
data/
```

---

## Step 2 — Build ALPR adoption dates

Run:

```bash
python scraper/build_atlas_alpr_launch_dates.py
```

This reads the Atlas ALPR dataset and attempts to identify the adoption/start date for each agency.

Check:

```text
data/atlas_alpr_agency_launch_dates.csv
```

Then review uncertain cases in:

```text
data/atlas_alpr_agency_launch_dates_manual_review.csv
```

The manual-review file is important because the script does not treat every date mentioned by Atlas as an adoption date.

---

## Step 3 — Collect Chicago police discipline data

Run:

```bash
python scraper/chicago_police_discipline.py
```

The script downloads current COPA and BIA data and creates the combined analysis files under:

```text
data/discipline/
```

Main outputs:

```text
chicago_police_discipline_cases.csv
chicago_police_discipline_by_month.csv
```

---

## Step 4 — Build the Flock sharing network

Run:

```bash
python scraper/flock_transparency_sharing.py
```

The script collects the available public agency-sharing network.

Outputs are stored under:

```text
data/flock_sharing/
```

For Chicago, start with:

```text
chicago_summary.csv
```

For the complete network, use:

```text
flock_sharing_edges.csv
```

The complete network can exceed GitHub's 100 MB file limit, so it may need to be regenerated locally rather than downloaded from the repository.

---

## Step 5 — Collect FBI Monthly Outcomes

Open `scraper/fbi_agency_clearances.py` and paste your key into the marked `API_KEY = ""` line. Keep a pasted key out of GitHub; an `FBI_API_KEY` environment variable is also supported.

Collect Illinois offenses, clearances, and arrests:

```bash
python scraper/fbi_agency_clearances.py --include-arrests
```

For offenses and clearances only, omit `--include-arrests`. For all 50 states and DC:

```bash
python scraper/fbi_agency_clearances.py --states ALL --include-arrests --out-dir data/fbi_clearances_us
```

Successful raw downloads are cached. Rerunning reuses them and retries unfinished requests; `--refresh` redownloads responses. A full Illinois run with arrests involves 16,650 requests using the current 925-agency directory and may take hours.

See [FBI collection instructions](docs/FBI_Clearance_Collection.md).

## Step 6 — Build the Atlas Index

Download or refresh the full Atlas dataset and calculate the index:

```bash
python scraper/build_atlas_absorptive_capacity.py --download-full
```

To reuse the saved full export, omit `--download-full`. No API key is needed.

For evidence explicitly dated before 2021:

```bash
python scraper/build_atlas_absorptive_capacity.py --cutoff-year 2020 --out-dir data/atlas_absorptive_capacity_pre2021
```

Undated evidence is excluded from the cutoff version. Article publication dates are not automatically treated as adoption dates. A common 2020 cutoff is not a valid pre-treatment baseline for agencies treated earlier.

See [Atlas index method and instructions](docs/Atlas_Absorptive_Capacity.md).

## Verify the New Scripts

```bash
python -m unittest discover -s tests -v
```

Development checks passed: six FBI-parser tests and 19 Atlas-index tests. They cover missing values, zeros, code/payload parsing, agency attribution, plans versus adoption, repeated evidence, Flock exclusion, and timing.

---

# Pipeline Summary

| Source | Research output |
|---|---|
| DeFlock / OSM | Camera locations and first-mapped dates |
| Atlas ALPR summaries | Agency adoption-date candidates and manual review |
| Full Atlas export | Documented technology experience and absorptive-capacity proxy |
| COPA + BIA | Chicago misconduct source records and preliminary monthly counts |
| FBI Crime Data Explorer | Agency-month offenses, clearances, and optional arrests |
| Public Flock sharing snapshots | Agency-to-agency access relationships |

These streams still require validated timing, agency matching, and outcome definitions before constructing the final research panel.

---

# Current Status

### Available

- Chicago ALPR camera locations
- Camera first-mapped dates from OSM history
- Police-department ALPR adoption-date extraction from Atlas
- Manual-review system for uncertain adoption dates
- Chicago COPA complaint data
- Chicago BIA misconduct/disciplinary data
- Agency-to-agency Flock sharing network
- Chicago-related Flock sharing exports; the current filter includes other agencies with Chicago in their names and needs refinement
- FBI monthly collection script, Illinois ORI directory, and successful Chicago pilot
- Full Atlas download and agency technology-experience index
- Sentence-level adoption evidence audit and pre-2021 Atlas version

### Still Needed / Under Validation

- Exact camera installation/operational dates where available
- Manual validation of uncertain Atlas dates
- Contract dates where better adoption dates cannot be found
- Historical start dates for Flock sharing relationships
- Final selection of police outcome variables
- Completion and coverage audit of the statewide FBI batch
- Deduplication and findings mapping for COPA/BIA outcomes
- Manual validation of Atlas adoption sentences, candidate ORIs, and pre-treatment dates
- Construct validity of the proposed absorptive-capacity proxy

---

## Current Research Priority

The immediate priority is obtaining the most defensible **police-department-level ALPR adoption dates**.

The overall workflow is:

1. Identify ALPR agencies and establish treatment timing.
2. Validate agency identifiers and uncertain adoption dates.
3. Distinguish direct ownership from shared access.
4. Collect and validate police outcomes and reporting coverage.
5. Measure technology experience before treatment.
6. Construct the agency-time panel and develop the empirical design.

## Work Completed — October 6, 2026

- Reviewed repository scripts and saved datasets, identifying timing, aggregation, and agency-filter issues.
- Built the FBI monthly collector with paste-key setup, separate clearance/arrest outputs, resumable caching, and audit files.
- Retrieved the 925-agency Illinois directory and completed a Chicago motor-vehicle-theft pilot, including supplemental arrest categories.
- Started the Illinois clearance batch. The last saved checkpoint inspected contains **300 processed requests and no recorded failures**; no final run metadata exists, so statewide completion is not claimed.
- Downloaded the full Atlas export and built the adoption-evidence index and audit outputs.
- Produced snapshot and explicitly dated pre-2021 versions, with candidate identifier conflicts flagged.
- Passed all 25 tests for the two new scripts.

The new scripts, data, and documentation were prepared in the working copy. They have not been pushed to GitHub in this session.
