"""CRUD + time-series endpoints backed by MySQL."""
from datetime import datetime
from typing import List

import mysql.connector
from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_mysql
from schemas import SOURCES, RecordCreate, RecordOut, RecordUpdate, to_naive_utc

router = APIRouter(prefix="/sql/records", tags=["MySQL"])

DUPLICATE_KEY = 1062


def load_records(cur, where="", params=(), order="ASC", limit=None, offset=0):
    """Read records (plus their 7 generation values) in the same shape for every endpoint."""
    assert order in ("ASC", "DESC")  # only constants from this file are ever passed
    sql = ("SELECT record_id, recorded_at, consumption, production FROM energy_records "
           f"{where} ORDER BY recorded_at {order}")
    params = tuple(params)
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params += (limit, offset)
    cur.execute(sql, params)
    recs = cur.fetchall()
    if not recs:
        return []

    ids = [r["record_id"] for r in recs]
    marks = ",".join(["%s"] * len(ids))
    cur.execute(
        "SELECT g.record_id, s.source_name, g.output_value FROM generation g "
        "JOIN energy_sources s ON s.source_id = g.source_id "
        f"WHERE g.record_id IN ({marks})", ids)
    gen = {}
    for g in cur.fetchall():
        gen.setdefault(g["record_id"], {})[g["source_name"]] = g["output_value"]

    return [{
        "id": r["record_id"],
        "timestamp": r["recorded_at"],
        "consumption": r["consumption"],
        "production": r["production"],
        "generation": gen.get(r["record_id"], {}),
    } for r in recs]


def get_or_404(cur, record_id):
    rows = load_records(cur, "WHERE record_id = %s", (record_id,))
    if not rows:
        raise HTTPException(404, f"Record {record_id} not found")
    return rows[0]


# ---- time-series queries (declared before /{record_id} so the paths don't clash) ----

@router.get("/latest", response_model=RecordOut, summary="Latest record")
def latest(conn=Depends(get_mysql)):
    cur = conn.cursor(dictionary=True)
    rows = load_records(cur, order="DESC", limit=1)
    if not rows:
        raise HTTPException(404, "No records in the database")
    return rows[0]


@router.get("/range", response_model=List[RecordOut], summary="Records by date range")
def by_range(
    start: datetime = Query(..., description="e.g. 2023-01-01T00:00:00"),
    end: datetime = Query(..., description="e.g. 2023-01-02T00:00:00"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    conn=Depends(get_mysql),
):
    start, end = to_naive_utc(start), to_naive_utc(end)
    if start > end:
        raise HTTPException(400, "start must not be after end")
    cur = conn.cursor(dictionary=True)
    return load_records(cur, "WHERE recorded_at BETWEEN %s AND %s", (start, end),
                        limit=limit, offset=offset)


# ---- CRUD ----

@router.post("", response_model=RecordOut, status_code=201, summary="Create a record")
def create(body: RecordCreate, conn=Depends(get_mysql)):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "INSERT INTO energy_records (recorded_at, consumption, production) VALUES (%s,%s,%s)",
            (body.timestamp, body.consumption, body.production))
        record_id = cur.lastrowid
        cur.execute("SELECT source_name, source_id FROM energy_sources")
        ids = {r["source_name"]: r["source_id"] for r in cur.fetchall()}
        gen = body.generation.model_dump()
        cur.executemany(
            "INSERT INTO generation (record_id, source_id, output_value) VALUES (%s,%s,%s)",
            [(record_id, ids[name], gen[name]) for name in SOURCES])
        conn.commit()
    except mysql.connector.IntegrityError as e:
        conn.rollback()
        if e.errno == DUPLICATE_KEY:
            raise HTTPException(409, "A record with this timestamp already exists")
        raise
    return get_or_404(cur, record_id)


@router.get("", response_model=List[RecordOut], summary="List records (paged)")
def list_records(limit: int = Query(20, ge=1, le=1000), offset: int = Query(0, ge=0),
                 conn=Depends(get_mysql)):
    cur = conn.cursor(dictionary=True)
    return load_records(cur, limit=limit, offset=offset)


@router.get("/{record_id}", response_model=RecordOut, summary="Get one record")
def read(record_id: int, conn=Depends(get_mysql)):
    return get_or_404(conn.cursor(dictionary=True), record_id)


@router.put("/{record_id}", response_model=RecordOut, summary="Update a record")
def update(record_id: int, body: RecordUpdate, conn=Depends(get_mysql)):
    cur = conn.cursor(dictionary=True)
    get_or_404(cur, record_id)

    changes = body.model_dump(exclude_none=True)
    gen_changes = changes.pop("generation", {})
    if not changes and not gen_changes:
        raise HTTPException(400, "Nothing to update")

    column_for = {"timestamp": "recorded_at", "consumption": "consumption",
                  "production": "production"}
    try:
        if changes:
            sets = ", ".join(f"{column_for[k]} = %s" for k in changes)  # keys come from the model
            cur.execute(f"UPDATE energy_records SET {sets} WHERE record_id = %s",
                        (*changes.values(), record_id))
        for name, value in gen_changes.items():  # names come from the model
            cur.execute(
                "UPDATE generation SET output_value = %s WHERE record_id = %s AND source_id = "
                "(SELECT source_id FROM energy_sources WHERE source_name = %s)",
                (value, record_id, name))
        conn.commit()
    except mysql.connector.IntegrityError as e:
        conn.rollback()
        if e.errno == DUPLICATE_KEY:
            raise HTTPException(409, "Another record already has this timestamp")
        raise
    return get_or_404(cur, record_id)


@router.delete("/{record_id}", summary="Delete a record")
def delete(record_id: int, conn=Depends(get_mysql)):
    cur = conn.cursor(dictionary=True)
    get_or_404(cur, record_id)
    cur.execute("DELETE FROM energy_records WHERE record_id = %s", (record_id,))  # cascades
    conn.commit()
    return {"deleted": record_id}