# Assignment 2 — Data Pipeline & Pace Tool
**Candidate Submission**  
*As-of Date: 1 October 2026*

---

## Part 1: Clean and Normalise

### 1A · Harbour Inn: Cleaning Log
Rules listed in order of application:

1. **Standardize channel casing** → **334 rows affected** → Channels had mixed casing (`booking.com`, `BOOKING.COM`). Normalized to standard TitleCase (`Booking.com`, `Airbnb`, `Expedia`, `Direct`).
2. **Deduplicate reservation records** → **14 rows affected** → 14 duplicate `ReservationID` pairs (28 rows total) were identical exports once casing was fixed. Dropped duplicates; 1,477 reservations retained.
3. **Parse dates (`dd/mm/yyyy`)** → **1,477 rows affected** → Strictly parsed day-first dates to prevent month/day swaps. Verified `CheckOut - CheckIn == Nights` across all rows.
4. **Fix nightly rate data entry errors** → **6 rows affected** → On 6 multi-night bookings, total revenue was accidentally entered as the nightly rate. Fixed by recalculating: `nightly_rate_net = RoomRevenue / Nights`.
5. **Resolve missing room numbers** → **7 rows affected** → 7 confirmed bookings had `Room == NaN`. Checked physical inventory: 4 had only one room open in their category; 3 had open rooms without conflict. Assigned rooms and flagged `is_room_inferred = True`.
6. **Flag post-check-in bookings** → **5 rows affected** → `BookedOn` was after `CheckIn` (retroactive ledger entries or walk-ins). Stays retained and flagged `is_booked_post_checkin = True`.
7. **Exclude cancellations from occupied nights** → **54 rows affected** → 54 bookings were `Cancelled`. Kept in canonical reservation table for auditing, but excluded from the 3,310 occupied room-nights (and checkout days excluded).

**Outputs:**
- `harbour_inn_canonical.csv` (1,477 reservations)
- `harbour_inn_occupied_nights.csv` (3,310 room-nights)

---

### 1B · Pine Ridge Cabins: Mapping & Assumptions
Minimum transformation to the canonical schema:
- **Net Rate:** Stripped 12% sales tax: `nightly_rate_net = (Total Price / 1.12) / Nights`.
- **Swapped Dates (6 rows):** Arrival was after Departure (e.g. Aug 17 to Aug 16). Swapped back to valid stay intervals and flagged `is_date_swapped = True`.
- **Missing Departures (4 rows):** Left `check_out`, `nights`, and `nightly_rate_net` empty rather than making up fake dates. Flagged `is_missing_departure = True`.
- **Schema Mapping:** Mapped `conf_no` → `reservation_id`, `state` (`OK`/`CANX`) → `status`, `Unit` → `unit`, `Category` → `unit_type`, `Source` → `channel`.

**Output:**
- `pine_ridge_canonical.csv` (909 reservations)

---

## Part 2: Inherit and Fix (`existing_pace.py`)

### Issues Found in Inherited Script:
1. **Date Parsing Corruption:** Used `format="mixed"`, which read `05/10/2026` as May 10th. Caused 38–41 rooms booked per day on an 8-room property. **Fix:** Used explicit `format="%d/%m/%Y"`.
2. **Double-Counted Checkout Days:** Loop used `while d <= CheckOut:`, counting the departure date as an occupied night. **Fix:** Changed to `while d < CheckOut:`.
3. **Included Cancelled Bookings:** Never filtered out `Status == 'Cancelled'`, inflating room counts. **Fix:** Added `df[df["Status"] != "Cancelled"]`.
4. **Day-of-Week Misalignment:** Subtracted 365 days, comparing Thursdays to Wednesdays. **Fix:** Used 364 days (52 full weeks) so weekdays align: `day - pd.Timedelta(days=364)`.
5. **Missing Historical As-Of Cutoff:** `ly_on_books` counted all bookings ever made (`ly_final`) instead of bookings made on or before 1 Oct 2025. **Fix:** Added filter `nights["booked_on"] <= 2025-10-01`.

**Output:**
- `harbour_pace.csv` (90 dates, 1 Oct to 29 Dec 2026)

---

## Part 3: Read the Output

### 1. Signal Breakdown (90 dates):
- **FULL:** 0 (0%)
- **AHEAD:** 34 (37.8%)
- **ON:** 32 (35.6%)
- **WATCH:** 1 (1.1%) — `2026-10-17`
- **BEHIND:** 23 (25.6%)

---

### 2. Top 3 Dates to Investigate:
1. **Sat 10 Oct (`AHEAD` | on_books: 6, ly_on_books: 3, ly_final: 4):**
   - 75% full at 9 days out, booking at double last year's pace.
   - **Action:** Raise rates on the remaining 2 rooms to maximize RevPAR rather than selling out cheaply.
2. **Sat 17 Oct (`WATCH` | on_books: 3, ly_on_books: 4, ly_final: 6):**
   - The only `WATCH` date in the 90 days. Only 3 rooms booked while Friday 16 Oct has 5 rooms booked.
   - **Action:** Check why Saturday is lagging—verify if a minimum stay rule is blocking single-night Saturday bookings or if rates are uncompetitive.
3. **Sun 25 Oct (`BEHIND` | on_books: 1, ly_on_books: 3, ly_final: 6):**
   - Earliest acute lag date in October (deficit of 2 rooms vs LY pace, 5 from LY finish).
   - **Action:** Push shoulder-night promotions (e.g. discounted Sunday add-on for weekend guests).

---

### 3. Challenging the Owner's Conclusion:
> *Owner: “October finished at about 130 room-nights last year and we’ve got about 100 on the books. We’re 20% behind. Drop the rates.”*

**What is wrong:**
- **Apples to Oranges:** The owner is comparing today's advance bookings (101) against last year's month-end total (131). October 2026 has just begun.
- **We are +62.9% AHEAD:** On 1 October 2025, last year only had **62 room-nights** on the books. Today we have **101**. We are 39 room-nights ahead of last year at the same point in time.
- **Dropping rates is a mistake:** We already hold 77% of last year's total month volume ($101 / 131$). Last year picked up 69 rooms in-the-month; matching that puts us at 170 rooms (68.5% occupancy vs 52.8% last year). Slashing rates now would dilute ADR and cause early, cheap sell-outs.
- **What to look at instead:** Weekly pickup velocity, date-level demand spikes, and achieved ADR.

---

## Part 4: Think

### 4. Weaknesses in the Pace Logic:
1. **Net Revenue & Commission Blindness:** The model treats all rooms as equal volume. But a direct booking at \$200 has 0% commission (\$200 net), while an Expedia booking at \$200 has 20% commission (\$160 net). A date flagged `AHEAD` via OTAs can actually generate less cash than last year.
2. **Ignores Booking Window Dynamics:** The model is a static snapshot. It doesn't track pickup velocity over the last 7 days or macro lead-time shifts. If traveler booking windows shrunk from 60 to 14 days, cutting rates at 45 days out because a date is `BEHIND` needlessly discounts inventory that would naturally book later at full price.

---

### 5. Scaling to 20 Properties across 6 PMSs:
1. **Decoupled Ingestion Adapters:** Build dedicated PMS connectors that normalize raw data into the canonical schema with automated validation tests (e.g. Pydantic) before running pace calculations.
2. **Centralized Database Snapshots:** Replace local CSVs with an automated database pipeline (Airflow/Prefect) that logs weekly Monday snapshots, ensuring consistent historical comparison points.

---

### 6. Build Next:
- **An Exception-Driven Action Matrix:** Across 20 properties, associates face 1,800 dates weekly. Instead of raw tables, build an engine that sorts dates by **revenue-at-risk** and outputs specific recommendations:
  - High pace + low remaining capacity → *Raise rate by 10%*
  - Low pace + close-in lead time → *Drop minimum stay or run promotion*
