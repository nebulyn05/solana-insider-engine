from collections.abc import Generator

import psycopg2
from psycopg2.extensions import connection

from app.config.settings import settings


def get_connection() -> connection:
    return psycopg2.connect(settings.database_url)


def connection_scope() -> Generator[connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
