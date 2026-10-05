"""
map_pine_ridge.py
Transforms pine_ridge_export.csv to the canonical reservation-level schema.
Schema: property, unit, unit_type, check_in, check_out, booked_on, channel, nightly_rate_net, nights
"""
import pandas as pd
import numpy as np

def map_pine_ridge(raw_csv_path="pine_ridge_export.csv"):
    df_raw = pd.read_csv(raw_csv_path)
    print(f"Loaded {len(df_raw)} raw rows from {raw_csv_path}")

    df = df_raw.copy()

    # 1. Property identifier
    df['property'] = 'Pine Ridge Cabins'

    # 2. Reservation ID & Status
    df['reservation_id'] = df['conf_no'].astype(str)
    status_map = {'OK': 'Confirmed', 'CANX': 'Cancelled'}
    df['status'] = df['state'].map(status_map)

    # 3. Unit and Unit Type
    df['unit'] = df['Unit']
    df['unit_type'] = df['Category']

    # 4. Dates parsing & handling anomalies
    # Arrival and Departure are ISO format (YYYY-MM-DD)
    arr_dt = pd.to_datetime(df['Arrival'])
    dep_dt = pd.to_datetime(df['Departure'])

    # Handle swapped dates (Arrival > Departure) in 6 records
    date_swapped_mask = (arr_dt > dep_dt) & dep_dt.notna()
    print(f"Detected {date_swapped_mask.sum()} records with swapped Arrival/Departure dates.")

    # Swap dates where arrival > departure
    fixed_arr = arr_dt.copy()
    fixed_dep = dep_dt.copy()
    fixed_arr[date_swapped_mask] = dep_dt[date_swapped_mask]
    fixed_dep[date_swapped_mask] = arr_dt[date_swapped_mask]

    df['check_in_dt'] = fixed_arr
    df['check_out_dt'] = fixed_dep
    df['check_in'] = fixed_arr.dt.strftime('%Y-%m-%d')
    df['check_out'] = fixed_dep.dt.strftime('%Y-%m-%d')

    # BookedOn date from Created (strip time component)
    created_dt = pd.to_datetime(df['Created'])
    df['booked_on'] = created_dt.dt.strftime('%Y-%m-%d')

    # 5. Nights calculation
    missing_dep_mask = df['Departure'].isna()
    print(f"Detected {missing_dep_mask.sum()} records with missing Departure.")
    df['nights'] = (df['check_out_dt'] - df['check_in_dt']).dt.days

    # 6. Channel standardisation
    source_map = {
        'airbnb': 'Airbnb', 'Airbnb': 'Airbnb',
        'vrbo': 'Vrbo', 'Vrbo': 'Vrbo',
        'website': 'Website', 'Website': 'Website',
        'phone': 'Phone', 'Phone': 'Phone'
    }
    df['channel'] = df['Source'].map(source_map)

    # 7. Net nightly rate (deduct 12% tax)
    # Total Price (incl. tax) has 12% tax -> Net Price = Total Price / 1.12
    # Nightly Rate Net = Net Price / nights
    df['net_price'] = df['Total Price (incl. tax)'] / 1.12
    df['nightly_rate_net'] = np.where(
        df['nights'] > 0,
        (df['net_price'] / df['nights']).round(2),
        np.nan
    )

    # Flags for auditability
    df['is_date_swapped'] = date_swapped_mask
    df['is_missing_departure'] = missing_dep_mask

    canonical_cols = [
        'property', 'reservation_id', 'status', 'unit', 'unit_type',
        'check_in', 'check_out', 'booked_on', 'channel',
        'nightly_rate_net', 'nights', 'is_date_swapped', 'is_missing_departure'
    ]
    df_canonical = df[canonical_cols].copy()

    output_path = "pine_ridge_canonical.csv"
    df_canonical.to_csv(output_path, index=False)
    print(f"Successfully saved {output_path} with {len(df_canonical)} records.")

    return df_canonical

if __name__ == "__main__":
    map_pine_ridge()
