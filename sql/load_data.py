"""
load_data.py - load Electricity.csv into the MySQL database (electricity_db).

Usage (Git Bash, from the folder containing this file and the CSV):
    pip install pandas mysql-connector-python
    python load_data.py                         # uses Electricity.csv
    python load_data.py --csv Electricity_clean.csv

The password is read from the MYSQL_PASSWORD environment variable, or asked
for when you run the script. Do NOT hard-code it (it would end up on GitHub).
"""
import argparse
import os
import getpass

import pandas as pd

SOURCES = ["nuclear", "wind", "hydroelectric", "oil_and_gas", "coal", "solar", "biomass"]
BATCH = 5000


def prepare(csv_path):
    """Read the CSV and return a clean DataFrame with one row per hour."""
    df = pd.read_csv(csv_path, parse_dates=["DateTime"])
    # database-friendly column names: "Oil and Gas" -> "oil_and_gas"
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    n_raw = len(df)

    df = df.drop_duplicates()                              # exact duplicate rows
    n_exact = n_raw - len(df)
    df = df.drop_duplicates(subset="datetime", keep="first")  # repeated clock-change hours
    n_ts = n_raw - n_exact - len(df)
    df = df.sort_values("datetime").reset_index(drop=True)

    print(f"Rows in CSV: {n_raw}")
    print(f"Dropped exact duplicates: {n_exact}")
    print(f"Dropped repeated timestamps (kept first): {n_ts}")
    print(f"Rows to load: {len(df)}")
    return df


def load(df, host, port, user, password, database):
    import mysql.connector

    conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password, database=database
    )
    cur = conn.cursor()

    # start from empty tables so the script can be re-run safely
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    cur.execute("TRUNCATE TABLE generation")
    cur.execute("TRUNCATE TABLE energy_records")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    # 1) energy_records
    rows = [
        (r.datetime.to_pydatetime(), int(r.consumption), int(r.production))
        for r in df.itertuples(index=False)
    ]
    sql = "INSERT INTO energy_records (recorded_at, consumption, production) VALUES (%s, %s, %s)"
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i:i + BATCH])
    conn.commit()
    print(f"Inserted {len(rows)} rows into energy_records")

    # 2) look up ids
    cur.execute("SELECT source_name, source_id FROM energy_sources")
    source_ids = dict(cur.fetchall())
    cur.execute("SELECT recorded_at, record_id FROM energy_records")
    record_ids = {ts: rid for ts, rid in cur.fetchall()}

    # 3) generation (long format: one row per source per hour)
    gen_rows = []
    for r in df.to_dict("records"):
        rid = record_ids[r["datetime"].to_pydatetime()]
        for name in SOURCES:
            gen_rows.append((rid, source_ids[name], int(r[name])))
    sql = "INSERT INTO generation (record_id, source_id, output_value) VALUES (%s, %s, %s)"
    for i in range(0, len(gen_rows), BATCH):
        cur.executemany(sql, gen_rows[i:i + BATCH])
    conn.commit()
    print(f"Inserted {len(gen_rows)} rows into generation")

    cur.close()
    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="Electricity.csv")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", default="root")
    p.add_argument("--database", default="electricity_db")
    a = p.parse_args()

    pwd = os.environ.get("MYSQL_PASSWORD") or getpass.getpass("MySQL password: ")
    data = prepare(a.csv)
    load(data, a.host, a.port, a.user, pwd, a.database)
    print("Done.")