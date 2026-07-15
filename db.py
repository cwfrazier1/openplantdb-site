"""Postgres access for the OpenPlantDB social platform."""
import os
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor, register_uuid

register_uuid()  # return uuid columns as uuid.UUID and adapt UUID[] params correctly

_pool = None


def pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            1, 12,
            host=os.environ.get("OPDB_PG_HOST", "192.168.1.52"),
            port=int(os.environ.get("OPDB_PG_PORT", "5432")),
            dbname=os.environ.get("OPDB_PG_DB", "openplantdb"),
            user=os.environ.get("OPDB_PG_USER", "openplantdb"),
            password=os.environ["OPDB_PG_PASSWORD"],
            connect_timeout=5,
        )
    return _pool


@contextmanager
def db(commit=False):
    p = pool()
    conn = p.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit() if commit else conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def q1(sql, params=None, commit=False):
    with db(commit=commit) as cur:
        cur.execute(sql, params or ())
        return cur.fetchone() if cur.description else None


def qall(sql, params=None):
    with db() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def execute(sql, params=None):
    with db(commit=True) as cur:
        cur.execute(sql, params or ())
        return cur.fetchone() if cur.description else None
