# StayOasi - Pricing Associate Assignment 2
## Data Pipeline & Pace Tool

This repository contains the complete solution for Assignment 2, including data cleaning pipelines, cross-PMS canonical transformations, fixed pace tool, output datasets, and strategic revenue analysis.

---

### Project Structure & Deliverables

| File | Purpose | Brief Section |
|---|---|---|
| [`clean_harbour_inn.py`](clean_harbour_inn.py) | End-to-end cleaning pipeline for Harbour Inn export | Part 1A |
| [`harbour_inn_canonical.csv`](harbour_inn_canonical.csv) | Cleaned reservation-level canonical table (1,477 rows) | Part 1A |
| [`harbour_inn_occupied_nights.csv`](harbour_inn_occupied_nights.csv) | Expanded occupied nights table (3,310 rows) | Part 1A |
| [`map_pine_ridge.py`](map_pine_ridge.py) | Transformation mapping Pine Ridge export to canonical schema | Part 1B |
| [`pine_ridge_canonical.csv`](pine_ridge_canonical.csv) | Mapped Pine Ridge reservation table (909 rows) | Part 1B |
| [`existing_pace.py`](existing_pace.py) | Fixed weekly pace script with correct logic and signals | Part 2 |
| [`harbour_pace.csv`](harbour_pace.csv) | Final 90-day pace table (1 Oct – 29 Dec 2026) | Part 2 & 3 |
| [`ANALYSIS_AND_SUBMISSION.md`](ANALYSIS_AND_SUBMISSION.md) | Full submission report (Cleaning Log, Bug Audit, Parts 3 & 4 Analysis) | All Parts |

---

### How to Run

All scripts are written in standard Python 3 and require `pandas` and `numpy`.

#### 1. Run Harbour Inn Cleaning & Night Expansion (Part 1A)
```bash
python clean_harbour_inn.py
```
*Outputs: `harbour_inn_canonical.csv`, `harbour_inn_occupied_nights.csv`, and prints the Cleaning Log.*

#### 2. Run Pine Ridge Canonical Mapping (Part 1B)
```bash
python map_pine_ridge.py
```
*Outputs: `pine_ridge_canonical.csv`.*

#### 3. Run Harbour Inn Pace Tool (Part 2)
```bash
python existing_pace.py harbour_inn_export.csv
```
*Outputs: `harbour_pace.csv` (90 days, 1 Oct 2026 to 29 Dec 2026).*

---

### Canonical Schema Definition

Both properties are normalized into the unified reservation schema:
- `property`: Property name string
- `reservation_id`: Unique identifier
- `status`: Reservation status (`Confirmed` / `Cancelled`)
- `unit`: Assigned room / cabin unit
- `unit_type`: Room / cabin category
- `check_in`: Stay arrival date (`YYYY-MM-DD`)
- `check_out`: Stay departure date (`YYYY-MM-DD`)
- `booked_on`: Creation date (`YYYY-MM-DD`)
- `channel`: Standardized booking channel (`Airbnb`, `Booking.com`, `Direct`, `Expedia`, `Vrbo`)
- `nightly_rate_net`: Net room rate per night (pre-tax, gross ADR standard)
- `nights`: Stay length in nights (`check_out - check_in`)
