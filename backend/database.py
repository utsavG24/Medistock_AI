import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

POSTGRES_BIN = Path("C:/Program Files/PostgreSQL/18/bin")
if POSTGRES_BIN.exists():
    os.environ["PATH"] = f"{POSTGRES_BIN}{os.pathsep}{os.environ.get('PATH', '')}"
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(POSTGRES_BIN))

DEFAULT_SQLITE_PATH = str(BASE_DIR / "medistock.db")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True   # tests each connection before using it
    engine_kwargs["pool_recycle"] = 300     # recycle connections older than 5 min

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def ensure_schema():
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            columns = connection.execute(text("PRAGMA table_info(medicines)")).fetchall()
            if not any(column[1] == "is_active" for column in columns):
                connection.execute(text("ALTER TABLE medicines ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"))
            if not any(column[1] == "units_per_strip" for column in columns):
                connection.execute(text("ALTER TABLE medicines ADD COLUMN units_per_strip INTEGER NOT NULL DEFAULT 1"))
            if not any(column[1] == "price_basis" for column in columns):
                connection.execute(text("ALTER TABLE medicines ADD COLUMN price_basis VARCHAR NOT NULL DEFAULT 'unit'"))
            admin_columns = connection.execute(text("PRAGMA table_info(admins)")).fetchall()
            if admin_columns and not any(column[1] == "pharmacy_name" for column in admin_columns):
                connection.execute(text("ALTER TABLE admins ADD COLUMN pharmacy_name VARCHAR"))
            sales_columns = connection.execute(text("PRAGMA table_info(sales_history)")).fetchall()
            if sales_columns and not any(column[1] == "batch_id" for column in sales_columns):
                connection.execute(text("ALTER TABLE sales_history ADD COLUMN batch_id INTEGER"))
        else:
            connection.execute(text(
                "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
            ))
            connection.execute(text(
                "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS units_per_strip INTEGER NOT NULL DEFAULT 1"
            ))
            connection.execute(text(
                "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS price_basis VARCHAR NOT NULL DEFAULT 'unit'"
            ))
            connection.execute(text(
                "ALTER TABLE admins ADD COLUMN IF NOT EXISTS pharmacy_name VARCHAR"
            ))
            connection.execute(text(
                "ALTER TABLE sales_history ADD COLUMN IF NOT EXISTS batch_id INTEGER"
            ))