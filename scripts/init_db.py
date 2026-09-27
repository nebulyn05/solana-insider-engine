from pathlib import Path

from app.database.connection import get_connection


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "database" / "schema.sql"


def main() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(schema)
        conn.commit()
    print("PostgreSQL simulation schema initialized successfully.")


if __name__ == "__main__":
    main()
