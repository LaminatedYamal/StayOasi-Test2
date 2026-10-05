"""
existing_pace.py — Harbour Inn weekly pace check (fixed)
Computes, for each stay date in the next 90 days (1 Oct 2026 to 29 Dec 2026):
  date         stay date being evaluated
  days_out     days between date and as-of date (1 Oct 2026)
  on_books     rooms occupied on date booked on/before 1 Oct 2026
  ly_date      equivalent date last year (date - 364 days, matching day of week)
  ly_on_books  rooms occupied on ly_date booked on/before historical as-of (1 Oct 2025)
  ly_final     total rooms occupied on ly_date regardless of booking date
  capacity     total rooms available (8 rooms)
  signal       booking pace classification (FULL / AHEAD / ON / WATCH / BEHIND)

Usage: python existing_pace.py harbour_inn_export.csv
"""
import sys
import pandas as pd

AS_OF = pd.Timestamp("2026-10-01")
LY_AS_OF = pd.Timestamp("2025-10-01")
HORIZON_DAYS = 90
CAPACITY = 8

def _dt(s):
    # Harbour Inn exports use dd/mm/yyyy format strictly
    return pd.to_datetime(s, format="%d/%m/%Y")

def load(path):
    df = pd.read_csv(path)
    # Deduplicate duplicate reservation records if present
    df = df.drop_duplicates(subset=["ReservationID"])
    # Exclude cancelled bookings: cancelled reservations do not occupy rooms
    df = df[df["Status"] != "Cancelled"]
    for col in ("CheckIn", "CheckOut", "BookedOn"):
        df[col] = _dt(df[col])
    return df

def expand_nights(df):
    rows = []
    for r in df.itertuples(index=False):
        d = r.CheckIn
        # Checkout day is not an occupied night (d < r.CheckOut)
        while d < r.CheckOut:
            rows.append({"date": d, "booked_on": r.BookedOn, "rate": r.NightlyRate})
            d += pd.Timedelta(days=1)
    return pd.DataFrame(rows)

def pace_table(nights):
    out = []
    for i in range(HORIZON_DAYS):
        day = AS_OF + pd.Timedelta(days=i)
        days_out = i
        # 364 days shifts exactly 52 weeks, matching day of week
        ly_day = day - pd.Timedelta(days=364)
        
        # on_books: occupied on day, booked on or before as-of date
        on_books = nights[(nights["date"] == day) & (nights["booked_on"] <= AS_OF)].shape[0]
        
        # ly_on_books: occupied on ly_day, booked on or before historical as-of date (1 Oct 2025)
        ly_on_books = nights[(nights["date"] == ly_day) & (nights["booked_on"] <= LY_AS_OF)].shape[0]
        
        # ly_final: total occupied rooms on ly_day across all booking times
        ly_final = nights[(nights["date"] == ly_day)].shape[0]
        
        # Signal classification evaluated in strict order
        if on_books >= CAPACITY:
            signal = "FULL"
        elif on_books > ly_on_books:
            signal = "AHEAD"
        elif on_books == ly_on_books:
            signal = "ON"
        elif on_books >= 0.7 * ly_on_books:
            signal = "WATCH"
        else:
            signal = "BEHIND"
            
        out.append({
            "date": day.strftime("%Y-%m-%d"),
            "days_out": days_out,
            "on_books": on_books,
            "ly_date": ly_day.strftime("%Y-%m-%d"),
            "ly_on_books": ly_on_books,
            "ly_final": ly_final,
            "capacity": CAPACITY,
            "signal": signal
        })
    return pd.DataFrame(out)

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "harbour_inn_export.csv"
    df = load(path)
    nights = expand_nights(df)
    table = pace_table(nights)
    output_filename = "harbour_pace.csv"
    table.to_csv(output_filename, index=False)
    print(table.head(14).to_string(index=False))
    print(f"\n{len(table)} dates written to {output_filename}")
    print("\nSignal counts:")
    print(table["signal"].value_counts().to_string())
