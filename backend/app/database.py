import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not configured")

from urllib.parse import urlsplit
import os as _dev_os
# CELEBRITYSPICES_DEV_BACKEND_GUARD
if _dev_os.environ.get("CELEBRITYSPICES_DEV_DB_ALLOWED") != "1":
    raise RuntimeError("Development backend blocked: authorization required")
_dev_url = urlsplit(DATABASE_URL)
if _dev_url.hostname not in ("127.0.0.1", "localhost") or _dev_url.port != 55432 or _dev_url.path != "/celebrityspices_dev":
    raise RuntimeError("Development backend blocked: isolated PostgreSQL URL required")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
