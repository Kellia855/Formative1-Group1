"""
load_mongo.py - load Electricity.csv into MongoDB (database: electricity_db,
collection: energy_records).

Usage (Git Bash, from the folder containing this file and the CSV):
    pip install pandas pymongo
    python load_mongo.py                          # uses Electricity.csv
    python load_mongo.py --csv Electricity_clean.csv
    python load_mongo.py --uri "mongodb://localhost:27017"
"""
import argparse

import pandas as pd
from pymongo import ASCENDING, MongoClient

SOURCES = ["nuclear", "wind", "hydroelectric", "oil_and_gas", "coal", "solar", "biomass"]
BATCH = 5000


def prepare(csv_path):
    """Same cleaning rule as the SQL loader: one row per hour."""
    df = pd.read_csv(csv_path, parse_dates=["DateTime"])
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    n_raw = len(df)
    df = df.drop_duplicates()
    n_exact = n_raw - len(df)
    df = df.drop_duplicates(subset="datetime", keep="first")
    n_ts = n_raw - n_exact - len(df)
    df = df.sort_values("datetime").reset_index(drop=True)
    print(f"Rows in CSV: {n_raw} | exact duplicates dropped: {n_exact} | "
          f"repeated timestamps dropped: {n_ts} | rows to load: {len(df)}")
    return df


def to_documents(df):
    docs = []
    for r in df.to_dict("records"):
        docs.append({
            "timestamp": r["datetime"].to_pydatetime(),
            "consumption": int(r["consumption"]),
            "production": int(r["production"]),
            "generation": {name: int(r[name]) for name in SOURCES},
        })
    return docs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="Electricity.csv")
    p.add_argument("--uri", default="mongodb://localhost:27017")
    p.add_argument("--database", default="electricity_db")
    p.add_argument("--collection", default="energy_records")
    a = p.parse_args()

    docs = to_documents(prepare(a.csv))

    client = MongoClient(a.uri, serverSelectionTimeoutMS=5000)
    col = client[a.database][a.collection]

    col.delete_many({})                                   # safe to re-run
    for i in range(0, len(docs), BATCH):
        col.insert_many(docs[i:i + BATCH])
    col.create_index([("timestamp", ASCENDING)], unique=True)

    print(f"Inserted {col.count_documents({})} documents into "
          f"{a.database}.{a.collection}")
    print("Done.")


if __name__ == "__main__":
    main()