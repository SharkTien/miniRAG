from app.config.database import DatabaseManager

db = DatabaseManager()
with db.connect() as conn:
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS progress_stage VARCHAR(100) DEFAULT ''")
    conn.commit()
    print("Migration OK: added progress, progress_stage columns")
