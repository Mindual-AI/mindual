# db/init_db.py
# DB 초기화 실행 스크립트
# db/init_db.py
import sqlite3
from pathlib import Path
from src.config import DB_PATH

def init_db():
    db_path = Path(DB_PATH).resolve()
    schema_path = Path(__file__).with_name("schema.sql")
    if not schema_path.exists():
        raise FileNotFoundError(f"schema.sql not found at: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    print(f"[init_db] Using DB: {db_path}")
    print(f"[init_db] Using schema: {schema_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(schema_sql)
        conn.commit()

        # 테이블 목록 출력
        rows = conn.execute("""
          SELECT name FROM sqlite_master
          WHERE type IN ('table','view')
          ORDER BY name
        """).fetchall()
        print("[init_db] Objects created:")
        for (name,) in rows:
            print(" -", name)
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
