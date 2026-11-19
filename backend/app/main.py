from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.routers.inventory import router as inventory_router
from app.routers.orders import router as orders_router
from app.routers.shopify import router as shopify_router
from app.routers.token import router as token_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        print(f"Database startup check failed: {exc}")

    yield

    engine.dispose()


app = FastAPI(
    title="Operations Platform API",
    description=(
        "Backend API for inventory, receiving, shipping, "
        "employees, Shopify, and blockchain operations."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(inventory_router)
app.include_router(orders_router)
app.include_router(shopify_router)
app.include_router(token_router)


@app.get("/", tags=["System"])
def root():
    return {
        "service": "operations-api",
        "message": "Operations Platform API is running",
        "docs": "/docs",
    }


@app.get("/health", tags=["System"])
def health():
    return {
        "service": "operations-api",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/database/health", tags=["System"])
def database_health():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    """
                    SELECT service_name, status, created_at, updated_at
                    FROM system_status
                    WHERE service_name = 'operations-postgres'
                    """
                )
            ).mappings().first()

            if result is None:
                raise HTTPException(
                    status_code=503,
                    detail="Database status record is missing",
                )

            return {
                "database": "operations_db",
                "status": "healthy",
                "record": {
                    "service_name": result["service_name"],
                    "status": result["status"],
                    "created_at": result["created_at"].isoformat(),
                    "updated_at": result["updated_at"].isoformat(),
                },
            }

    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection failed: {exc.__class__.__name__}",
        ) from exc
