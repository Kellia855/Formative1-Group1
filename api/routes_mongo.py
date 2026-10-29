"""CRUD + time-series endpoints backed by MongoDB."""
from datetime import datetime
from typing import List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from database import get_collection
from schemas import RecordCreate, RecordOut, RecordUpdate, to_naive_utc

router = APIRouter(prefix="/mongo/records", tags=["MongoDB"])


def to_record(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "timestamp": doc["timestamp"],
        "consumption": doc["consumption"],
        "production": doc["production"],
        "generation": doc.get("generation", {}),
    }


def parse_id(record_id: str) -> ObjectId:
    try:
        return ObjectId(record_id)
    except (InvalidId, TypeError):
        raise HTTPException(422, "Invalid record id (expected a 24-character hex string)")


def get_or_404(col, oid: ObjectId) -> dict:
    doc = col.find_one({"_id": oid})
    if doc is None:
        raise HTTPException(404, f"Record {oid} not found")
    return to_record(doc)


# ---- time-series queries (declared before /{record_id}) ----

@router.get("/latest", response_model=RecordOut, summary="Latest record")
def latest(col=Depends(get_collection)):
    doc = col.find_one(sort=[("timestamp", DESCENDING)])
    if doc is None:
        raise HTTPException(404, "No records in the database")
    return to_record(doc)


@router.get("/range", response_model=List[RecordOut], summary="Records by date range")
def by_range(
    start: datetime = Query(..., description="e.g. 2023-01-01T00:00:00"),
    end: datetime = Query(..., description="e.g. 2023-01-02T00:00:00"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    col=Depends(get_collection),
):
    start, end = to_naive_utc(start), to_naive_utc(end)
    if start > end:
        raise HTTPException(400, "start must not be after end")
    cursor = (col.find({"timestamp": {"$gte": start, "$lte": end}})
              .sort("timestamp", 1).skip(offset).limit(limit))
    return [to_record(d) for d in cursor]


# ---- CRUD ----

@router.post("", response_model=RecordOut, status_code=201, summary="Create a record")
def create(body: RecordCreate, col=Depends(get_collection)):
    doc = body.model_dump()
    try:
        result = col.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "A record with this timestamp already exists")
    return get_or_404(col, result.inserted_id)


@router.get("", response_model=List[RecordOut], summary="List records (paged)")
def list_records(limit: int = Query(20, ge=1, le=1000), offset: int = Query(0, ge=0),
                 col=Depends(get_collection)):
    cursor = col.find().sort("timestamp", 1).skip(offset).limit(limit)
    return [to_record(d) for d in cursor]


@router.get("/{record_id}", response_model=RecordOut, summary="Get one record")
def read(record_id: str, col=Depends(get_collection)):
    return get_or_404(col, parse_id(record_id))


@router.put("/{record_id}", response_model=RecordOut, summary="Update a record")
def update(record_id: str, body: RecordUpdate, col=Depends(get_collection)):
    oid = parse_id(record_id)
    changes = body.model_dump(exclude_none=True)
    gen_changes = changes.pop("generation", {})
    fields = dict(changes)
    fields.update({f"generation.{k}": v for k, v in gen_changes.items()})
    if not fields:
        raise HTTPException(400, "Nothing to update")
    try:
        result = col.update_one({"_id": oid}, {"$set": fields})
    except DuplicateKeyError:
        raise HTTPException(409, "Another record already has this timestamp")
    if result.matched_count == 0:
        raise HTTPException(404, f"Record {record_id} not found")
    return get_or_404(col, oid)


@router.delete("/{record_id}", summary="Delete a record")
def delete(record_id: str, col=Depends(get_collection)):
    result = col.delete_one({"_id": parse_id(record_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, f"Record {record_id} not found")
    return {"deleted": record_id}