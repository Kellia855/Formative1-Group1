"""Electricity time-series API.

Run from this folder:
    uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI

import database
import routes_mongo
import routes_sql

app = FastAPI(
    title="Electricity Time-Series API",
    description="CRUD and time-series queries over the same hourly electricity data "
                "stored in MySQL (/sql/...) and MongoDB (/mongo/...).",
    version="1.0",
)
app.include_router(routes_sql.router)
app.include_router(routes_mongo.router)


@app.get("/", tags=["Health"])
def root():
    return {"message": "Electricity API is running. See /docs for the endpoints."}


@app.get("/health", tags=["Health"])
def health():
    status = {}
    try:
        database.ping_mysql()
        status["mysql"] = "ok"
    except Exception as e:  # report instead of crashing
        status["mysql"] = f"error: {e}"
    try:
        database.get_collection().database.client.admin.command("ping")
        status["mongodb"] = "ok"
    except Exception as e:
        status["mongodb"] = f"error: {e}"
    return status