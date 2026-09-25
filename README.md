# ALPR / Flock Camera Research Project

## Overview

This project collects data on **Automated License Plate Reader (ALPR)** adoption by U.S. police departments, with Chicago as the current main case.

The project addresses four questions:

1. Where are ALPR cameras located?
2. When did police departments begin using ALPRs?
3. What police misconduct/disciplinary data are available?
4. Which police departments can access other agencies' Flock data?

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

The pipeline combines:

- COPA cases
- COPA involved-officer records
- BIA involved-officer records

This allows us to examine:

- Complaints
- Misconduct categories
- Investigation findings
- Disciplinary outcomes, when available

**Outputs:**

`chicago_police_discipline_cases.csv` — Case-level data.

`chicago_police_discipline_by_month.csv` — Monthly aggregated outcomes.

---

### 4. Flock Data Sharing Across Agencies

Owning Flock cameras and having access to Flock data are not necessarily the same.

For example:

```text
Agency A owns Flock cameras
        ↓ shares data
Agency B can access the data
```

Therefore, an agency without its own cameras may still be exposed to Flock.

We collect public agency-to-agency sharing relationships derived from **Flock Transparency Portal** information.

**Outputs:**

`flock_sharing_edges.csv` — Full sharing network.

`chicago_access_edges.csv` — Relationships involving Chicago.

`chicago_summary.csv` — Simplified Chicago sharing information.

**Limitation:** we can identify sharing relationships, but we do not yet have reliable historical dates for when each relationship began.

---

# Setup

## 1. Clone the repository

```bash
git clone https://github.com/tinrt/flock_cams_project.git
cd flock_cams_project
```

## 2. Install Python packages

Python 3 is required.

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

# Pipeline Summary

```text
DeFlock / OSM
      ↓
Camera locations + first mapped dates

Atlas of Surveillance
      ↓
Police department ALPR adoption dates
      ↓
Manual validation of uncertain dates

COPA + BIA
      ↓
Chicago police misconduct / discipline outcomes

Flock Transparency data
      ↓
Agency-to-agency data-sharing network

                ↓

        Research Dataset
```

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
- Chicago-specific Flock sharing relationships

### Still Needed / Under Validation

- Exact camera installation/operational dates where available
- Manual validation of uncertain Atlas dates
- Contract dates where better adoption dates cannot be found
- Historical start dates for Flock sharing relationships
- Final selection of police outcome variables

---

## Current Research Priority

The immediate priority is obtaining the most defensible **police-department-level ALPR adoption dates**.

The overall workflow is:

```text
Identify ALPR agencies
        ↓
Determine adoption timing
        ↓
Validate uncertain dates
        ↓
Identify direct ownership + shared access
        ↓
Construct police outcome variables
        ↓
Develop empirical design
```