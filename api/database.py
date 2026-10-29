"""Database connections. Settings come from environment variables or a .env file."""
import os

from dotenv import load_dotenv
from mysql.connector import pooling
from pymongo import MongoClient

load_dotenv()

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "electricity_db"),
}
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DATABASE", "electricity_db")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "energy_records")

_pool = None
_mongo_client = None


def get_mysql():
    """FastAPI dependency: one pooled MySQL connection per request."""
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(pool_name="api_pool", pool_size=5, **MYSQL_CONFIG)
    conn = _pool.get_connection()
    try:
        yield conn
    finally:
        conn.close()  # returns it to the pool


def get_collection():
    """FastAPI dependency: the MongoDB collection."""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _mongo_client[MONGO_DB][MONGO_COLLECTION]


def ping_mysql():
    """Used by /health: open a connection, run SELECT 1, give it back."""
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(pool_name="api_pool", pool_size=5, **MYSQL_CONFIG)
    conn = _pool.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchall()
    finally:
        conn.close()