# StayOasi - Pricing Associate Assignment 2
**Candidate Submission: Data Pipeline & Pace Tool**  
*As-of Date: 1 October 2026*

---

## Executive Summary

This submission completes all requirements across Parts 1 through 4:
1. **Harbour Inn (Part 1A):** Fully cleaned and normalized reservation-level canonical table (`harbour_inn_canonical.csv`), expanded occupied-nights table (`harbour_inn_occupied_nights.csv`), and sequential cleaning log.
2. **Pine Ridge Cabins (Part 1B):** Minimum transformation mapping to the identical canonical schema (`pine_ridge_canonical.csv`) with full documentation of assumptions (tax deduction, swapped dates, missing departures).
3. **Pace Tool Fix (Part 2):** Audited and corrected `existing_pace.py`, resolving 5 critical logic bugs (date corruption, checkout night inflation, cancelled stays, day-of-week misalignment, and historical as-of lead-time filtering). Generated `harbour_pace.csv` covering 1 Oct to 29 Dec 2026.
4. **Analysis & Strategy (Parts 3 & 4):** Signal distribution analysis, priority dates to investigate, a detailed debunking of the owner's "drop rates" conclusion, structural weaknesses in the pace model, scaling architecture for 20 properties across 6 PMSs, and next-generation roadmap.

---

## Part 1: Clean and Normalise

### 1A · Harbour Inn: Cleaning Log & Canonical Schema

#### Cleaning Log (`rule → rows affected → reasoning`)

| # | Rule Applied | Rows Affected | Reasoning |
|---|---|:---:|---|
| **1** | **Standardize channel casing** | **334 rows** | Channel names were inconsistently cased (e.g., `'booking.com'`, `'BOOKING.COM'`, `'Booking.com'`; `'AIRBNB'`, `'airbnb'`, `'Airbnb'`). Normalized all to canonical TitleCase (`'Booking.com'`, `'Airbnb'`, `'Expedia'`, `'Direct'`). |
| **2** | **Deduplicate reservation records** | **14 rows** (28 rows total) | Identified 14 duplicate `ReservationID` pairs. Once channel casing was normalized in Rule 1, these records were identical duplicate exports. Retained the first occurrence and removed the 14 duplicate records (leaving 1,477 unique reservations). |
| **3** | **Parse dates with strict `%d/%m/%Y` format & validate duration** | **1,477 rows** | Explicitly parsed `CheckIn`, `CheckOut`, and `BookedOn` using strict day-first format to prevent month/day transposition errors. Validated that `(CheckOut - CheckIn).days == Nights` for 100% of rows. |
| **4** | **Reconcile NightlyRate data entry errors** | **6 rows** | In 6 multi-night reservations (`HI-10113`, `HI-10544`, `HI-10522`, `HI-11910`, `HI-10803`, `HI-11868`), `NightlyRate` equaled `RoomRevenue` directly, whereas `Commission` was accurately calculated on `RoomRevenue`. Corrected `nightly_rate_net = RoomRevenue / Nights`. |
| **5** | **Impute missing room assignments** | **7 rows** | 7 confirmed reservations had `Room == NaN`. Audited inventory availability across their stay dates for each corresponding `RoomType`. For 4 reservations, exactly one room was physically available; for the remaining 3, open rooms existed without overlap. Assigned available room and flagged with `is_room_inferred = True`. |
| **6** | **Flag post-check-in bookings (`BookedOn > CheckIn`)** | **5 rows** | 5 reservations recorded `BookedOn` after `CheckIn` (e.g., walk-ins or retroactive front-desk entries). Retained records without altering stay dates and tagged with `is_booked_post_checkin = True`. |
| **7** | **Segregate cancelled reservations for occupied nights** | **54 rows** | 54 reservations had `Status == 'Cancelled'`. Retained in canonical reservation table for auditing, but strictly excluded from the occupied nights expansion (`harbour_inn_occupied_nights.csv`, yielding 3,310 valid occupied nights). |

#### Output Files:
- `harbour_inn_canonical.csv`: 1,477 reservations. Columns: `property, reservation_id, status, unit, unit_type, check_in, check_out, booked_on, channel, nightly_rate_net, nights, is_room_inferred, is_booked_post_checkin`.
- `harbour_inn_occupied_nights.csv`: 3,310 occupied nights (checkout dates excluded).

---

### 1B · Pine Ridge Cabins: Mapping Assumptions & Canonical Output

#### Mapping Transformation
- **`property`**: Set constant `'Pine Ridge Cabins'`.
- **`reservation_id`**: Mapped from `conf_no`.
- **`status`**: Mapped PMS status codes: `'OK'` $\rightarrow$ `'Confirmed'`, `'CANX'` $\rightarrow$ `'Cancelled'`.
- **`unit`**: Mapped from `Unit` (Aspen, Birch, Cedar, Summit, Ridge).
- **`unit_type`**: Mapped from `Category` (Cabin, Lodge).
- **`check_in` / `check_out`**: Parsed ISO dates `Arrival` and `Departure`.
- **`booked_on`**: Extracted date portion `YYYY-MM-DD` from `Created` timestamp.
- **`channel`**: Normalized `Source` casing to TitleCase (`Airbnb`, `Vrbo`, `Website`, `Phone`).
- **`nightly_rate_net`**: Deducted 12% sales/lodging tax:
  $$\text{Net Price} = \frac{\text{Total Price (incl. tax)}}{1.12}, \quad \text{nightly\_rate\_net} = \frac{\text{Net Price}}{\text{nights}}$$

#### Documented Assumptions:
1. **12% Tax Deduction:** Per the brief, prices include 12% tax. Hospitality net revenue standard is pre-tax room revenue. Divided by `1.12` before dividing by nights.
2. **Inverted Arrival/Departure Dates (6 rows):** 6 records had `Arrival > Departure` (e.g., Arrival 2026-08-17, Departure 2026-08-16, resulting in $-1$ nights). In all 6 cases, `Created` preceded both dates, and swapping Arrival/Departure produced standard 1–3 night stays consistent with unit pricing. Swapped the dates and flagged with `is_date_swapped = True`.
3. **Missing Departure Dates (4 rows):** 4 records (`conf_no`: 10232, 10720, 10710, 10798) had missing `Departure`. Rather than fabricating checkout dates, retained as `NaN` nights / rate and explicitly flagged with `is_missing_departure = True`.

#### Output File:
- `pine_ridge_canonical.csv`: 909 mapped reservations. Columns: `property, reservation_id, status, unit, unit_type, check_in, check_out, booked_on, channel, nightly_rate_net, nights, is_date_swapped, is_missing_departure`.

---

## Part 2: Inherit and Fix (`existing_pace.py`)

### Summary of Material Issues Found

| Issue | What Was Wrong | How Found | What Was Changed |
|---|---|---|---|
| **1. Date Parsing Ambiguity** | Used `pd.to_datetime(s, format="mixed")`. Pandas defaulted to US `mm/dd/yyyy` for days $\le 12$, corrupting months (e.g., Oct 5 parsed as May 10). | Inspection of `existing_pace.py` showed 38–41 rooms booked per day on an 8-room property. | Changed to explicit format: `pd.to_datetime(s, format="%d/%m/%Y")`. |
| **2. Checkout Day Counted as Occupied** | Line 31 used `while d <= r.CheckOut:`, adding the checkout date as an occupied night (e.g. 3-night stay counted as 4). | Code review of expansion loop vs brief specification ("checkout day is not an occupied night"). | Changed condition to `while d < r.CheckOut:`. |
| **3. Cancelled Bookings Included** | Loaded raw CSV directly without filtering `Status == 'Cancelled'`. 54 cancelled reservations falsely inflated occupancy. | Checking raw status column and tracking room occupancy counts. | Added filter: `df = df[df["Status"] != "Cancelled"]`. |
| **4. Day-of-Week Misalignment (365 vs 364 Days)** | Line 40 used `day - Timedelta(days=365)`. This compared dates on different days of the week (e.g., Saturday vs Friday). | Checking day-of-week logic in brief: 52 weeks $\times 7 = 364$ days. | Changed to `ly_day = day - pd.Timedelta(days=364)`. |
| **5. Missing Historical As-Of Cutoff for `ly_on_books`** | Line 42 counted all bookings ever made for `ly_date` (`nights[nights["date"] == ly_day]`). This was `ly_final`, not `ly_on_books`. | Comparing definition of pace: pace requires same lead time (apples-to-apples). | Added filter: `nights[(nights["date"] == ly_day) & (nights["booked_on"] <= LY_AS_OF)]` where `LY_AS_OF = 2025-10-01`. |
| **6. Missing Schema & Signals** | Output lacked `days_out`, `ly_date`, `ly_final`, `capacity`, and the 5-tier signal classification. | Comparing script output to assignment requirements. | Added exact columns and evaluated signal rules in specified order. |

---

## Part 3: Read the Output

### 1. Signal Distribution (1 Oct – 29 Dec 2026, 90 Dates)

| Signal | Date Count | % of Horizon | Description |
|:---:|:---:|:---:|---|
| **FULL** | **0** | 0.0% | Max current on-books on any date is 6 rooms (Capacity = 8). |
| **AHEAD** | **34** | 37.8% | Current bookings exceed equivalent LY pace (`on_books > ly_on_books`). |
| **ON** | **32** | 35.6% | Current bookings match equivalent LY pace (`on_books == ly_on_books`). |
| **WATCH** | **1** | 1.1% | Current bookings between 70% and 100% of LY pace (`2026-10-17`). |
| **BEHIND** | **23** | 25.6% | Current bookings are strictly below 70% of LY pace. |
| **Total** | **90** | **100.0%** | Full 90-day evaluation window. |

---

### 2. What Deserves Attention? Top 3 Dates to Investigate

#### **Date 1: Saturday 10 October 2026 (`2026-10-10`) — Days Out: 9**
- **Metrics:** `on_books = 6`, `ly_on_books = 3`, `ly_final = 4`, `capacity = 8`, `signal = AHEAD`
- **Why investigate:** 
  - Harbour Inn is already at **75% occupancy** with 9 days to go, pacing at **$2\times$** last year’s booking volume (which only finished at 4 rooms total).
  - With only 2 rooms remaining, this is an immediate **yield management opportunity**. Rather than allowing the last 2 rooms to sell out at standard base rates, we should **raise rates immediately** or enforce a 2-night minimum length of stay (MLOS) spanning Friday/Sunday to maximize Total RevPAR.

#### **Date 2: Saturday 17 October 2026 (`2026-10-17`) — Days Out: 16**
- **Metrics:** `on_books = 3`, `ly_on_books = 4`, `ly_final = 6`, `capacity = 8`, `signal = WATCH`
- **Why investigate:** 
  - This is the **only date in the entire 90-day horizon flagged with `WATCH`** ($3 / 4 = 75\% \ge 70\%$).
  - For a prime Saturday in mid-October, having only 3 rooms booked (37.5% occupancy) while Friday 16 October already has 5 rooms booked indicates an **unbalanced weekend pattern**.
  - We need to investigate whether a minimum stay restriction is blocking Saturday-only bookings, or if our Saturday rate is priced too high relative to Friday and local competitors.

#### **Date 3: Sunday 25 October 2026 (`2026-10-25`) — Days Out: 24**
- **Metrics:** `on_books = 1`, `ly_on_books = 3`, `ly_final = 6`, `capacity = 8`, `signal = BEHIND`
- **Why investigate:** 
  - This is the earliest acute lag date in October. With only 1 room booked vs 3 at the same point last year, it has a significant deficit towards last year’s finish of 6 rooms.
  - Sunday nights can suffer from shoulder-night friction. We should inspect whether surrounding weekend stays (Fri/Sat 23–24 Oct) are capturing Sunday extensions, check channel distribution, or launch targeted promotional fencing (e.g., "extend your weekend" discounts).

---

### 3. Challenge the Conclusion

> **Owner Quote:** *“October finished at about 130 room-nights last year and we’ve got about 100 on the books. We’re 20% behind. Drop the rates.”*

#### **What is fundamentally wrong with that conclusion?**
The owner is committing the classic revenue management fallacy of **comparing apples to oranges**:
1. **Flawed Benchmark:** The owner is comparing **current on-the-books bookings as of 1 October** against **last year’s finalized month-end total**. The month of October 2026 hasn't happened yet!
2. **We are NOT 20% behind — we are 62.9% AHEAD:**
   - On 1 October 2025, last year had only **62 room-nights** on the books.
   - On 1 October 2026, we currently have **101 room-nights** on the books.
   - At the exact same lead time, we have captured **39 additional room-nights** (+62.9% ahead of last year's pace).
   - In fact, we have already banked **77.1%** of last year’s entire final volume ($101 / 131$) before day 1 of the month has even elapsed.
3. **Dropping rates would be financially damaging:**
   - Last year, Harbour Inn picked up $131 - 62 = 69$ room-nights during the month of October.
   - Total monthly capacity is 248 room-nights ($31 \text{ days} \times 8 \text{ rooms}$). We are already at 40.7% monthly occupancy on day 1.
   - If we merely match last year’s in-the-month pickup (69 room-nights), we will finish at $101 + 69 = 170$ room-nights (**68.5% occupancy**, well ahead of last year's 52.8%).
   - If pickup continues at current pace, October will exceed 80% occupancy. Dropping rates would dilute ADR, induce premature sell-outs on high-demand dates, and leave substantial revenue on the table.

#### **What we can and cannot conclude:**
- **What we CAN conclude:** Our booking curve has shifted earlier (longer booking window or stronger early demand). Overall demand for October is significantly stronger than last year.
- **What we CANNOT conclude:** We cannot conclude that overall volume is lagging, nor can we conclude that rates should be lowered across the board.
- **What to look at instead:**
  1. **Pickup velocity:** How many bookings materialized in the last 7, 14, and 30 days.
  2. **Date-level granularity:** Differentiate high-occupancy dates (e.g. 10 Oct at 6 rooms booked—where we should raise rates) from soft dates (e.g. 25 Oct at 1 room).
  3. **ADR & Revenue Pace:** Check current Achieved ADR vs LY. If current ADR is also higher, RevPAR is surging.
  4. **Lead time distribution & channel mix:** Ensure OTA distribution and direct mix remain healthy.

---

## Part 4: Think

### 4. What’s Missing? Weaknesses in the Pace Logic

#### **Weakness 1: Rate & Channel Profitability Blindness (Volume vs Net Contribution)**
- **Explanation:** The pace model only tracks physical room counts (`on_books`), completely ignoring Achieved ADR (Average Daily Rate) and, crucially, **Channel Commission / Net Contribution**. In the Harbour Inn dataset, OTA commissions range from **0% on Direct bookings** to **15% on Booking.com** and up to **22% on Expedia**. Treating all booked rooms as identical volume masks significant revenue and profit leakage.
- **Concrete Failure Scenario:** Suppose for a weekend in mid-November, `on_books = 5` and `ly_on_books = 4`. The tool signals **`AHEAD`**. 
  - Last year, those 4 rooms were booked **Direct** at \$220/night with 0% commission, netting **\$880** in cash flow.
  - This year, the 5 rooms came through **Expedia** at \$180/night with a 20% commission (\$36/room), netting only \$144/room = **\$720** in cash flow.
  - Despite being labeled **`AHEAD`**, net contribution has actually **collapsed by 18%**. A pricing associate relying solely on the volume signal might hold rates or restrict inventory, unaware that poor channel mix is eroding profitability.

#### **Weakness 2: Zero Accounting for Pickup Velocity & Dynamic Booking Windows**
- **Explanation:** The model is a static point-in-time snapshot comparing today to 364 days ago. It does not measure the *first derivative* (the velocity of bookings picked up over the trailing 7 or 14 days) nor does it account for structural macro shifts in the customer booking curve.
- **Concrete Failure Scenario:** Consider a date 45 days out in late November where `on_books = 1` vs `ly_on_books = 3`. The tool flags **`BEHIND`**.
  - However, market-wide booking lead times have compressed from 60 days down to 14 days due to changing traveler habits. 
  - If the pricing associate reacts mechanically to the `BEHIND` flag by slashing rates at 45 days out, they will unnecessarily discount rooms that would have naturally booked at full price within the closer-in 14-day window, resulting in severe rate dilution and lost RevPAR.

---

### 5. Scale It: Automating for 20 Properties across 6 PMSs Every Monday

If deploying this pipeline across 20 properties and 6 different PMS systems, the first two architectural changes to implement are:

1. **Decoupled Ingestion & Normalization Layer (Connector Pattern with Schema Validation):**
   - Implement dedicated ingestion adapters for each PMS (e.g., Mews, Cloudbeds, Guesty, Opera) that abstract raw PMS idiosyncrasies (date formats, tax inclusions, cancellation codes, room naming).
   - Use strict data validation contracts (e.g., Pydantic or Great Expectations) that normalize all incoming data into the canonical schema before downstream pace calculations run. If an export has schema anomalies or missing fields, it raises automated alerts rather than corrupting calculations.
2. **Centralized Data Store with Automated As-Of Snapshotting & Batch Scheduling:**
   - Replace manual CSV file passing with a centralized database (or data warehouse like BigQuery/PostgreSQL) managed by an orchestrator (e.g., Apache Airflow, Prefect, or scheduled GitHub Actions).
   - Capture point-in-time weekly snapshots every Monday at 00:00 UTC. This guarantees true, immutable historical snapshots for pace comparisons across properties without having to retroactively re-parse historical CSV files.

---

### 6. Build Next: Strategic Roadmap for Weekly Operations

If this became a core weekly tool, I would build an **Exception-Driven Action Matrix & Dynamic Recommendation Engine**:
- **Why:** In weekly revenue management across multiple properties, associates do not have time to manually scan 90 dates $\times$ 20 properties (1,800 rows). 
- **What it does:**
  1. **Automated Action Recommendations:** Combines Pace Signal, Remaining Unsold Capacity, Days Out, and Competitor Rate Positioning to generate clear pricing actions:
     - *Example:* `AHEAD` + `Days Out > 14` + `Capacity Remaining <= 2` $\rightarrow$ **Action: Raise Rate by +10%**.
     - *Example:* `BEHIND` + `Days Out < 14` + `Capacity Remaining >= 5` $\rightarrow$ **Action: Relax MLOS / Apply 10% Flash Promo**.
  2. **Priority Ranking (Revenue at Risk):** Sorts dates by expected revenue impact ($\text{Unsold Capacity} \times \text{Expected ADR}$), allowing the team to spend their first 30 minutes on the top 5 highest-leverage opportunities every Monday morning.
