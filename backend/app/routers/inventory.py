from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import SessionLocal
from app.inventory_movements import create_inventory_movement
from app.routers.shopify import push_inventory_to_shopify
from app.models import (
    InventoryItem,
    InventoryLevel,
    InventoryMovement,
    Warehouse,
)
from app.schemas import (
    InventoryAdjustmentCreate,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryMovementResponse,
    ReceivingCreate,
    ShippingCreate,
    WarehouseResponse,
)


router = APIRouter(tags=["Inventory"])


def get_database():
    database = SessionLocal()

    try:
        yield database
    finally:
        database.close()


@router.get(
    "/warehouses",
    response_model=list[WarehouseResponse],
)
def list_warehouses(database: Session = Depends(get_database)):
    statement = (
        select(Warehouse)
        .where(Warehouse.is_active.is_(True))
        .order_by(Warehouse.name)
    )

    return database.scalars(statement).all()


@router.get(
    "/inventory",
    response_model=list[InventoryItemResponse],
)
def list_inventory(database: Session = Depends(get_database)):
    statement = (
        select(InventoryItem)
        .options(selectinload(InventoryItem.inventory_levels))
        .order_by(InventoryItem.name)
    )

    return database.scalars(statement).all()


@router.get(
    "/inventory/{item_id}",
    response_model=InventoryItemResponse,
)
def get_inventory_item(
    item_id: int,
    database: Session = Depends(get_database),
):
    statement = (
        select(InventoryItem)
        .options(selectinload(InventoryItem.inventory_levels))
        .where(InventoryItem.id == item_id)
    )

    item = database.scalar(statement)

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    return item


@router.post(
    "/inventory",
    response_model=InventoryItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_item(
    payload: InventoryItemCreate,
    database: Session = Depends(get_database),
):
    warehouse = database.get(Warehouse, payload.warehouse_id)

    if warehouse is None or not warehouse.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found or inactive",
        )

    item = InventoryItem(
        sku=payload.sku.strip(),
        name=payload.name.strip(),
        description=payload.description,
        barcode=payload.barcode,
        unit_of_measure=payload.unit_of_measure,
        shopify_product_id=payload.shopify_product_id,
        shopify_variant_id=payload.shopify_variant_id,
        shopify_inventory_item_id=payload.shopify_inventory_item_id,
    )

    database.add(item)

    try:
        database.flush()

        level = InventoryLevel(
            inventory_item_id=item.id,
            warehouse_id=payload.warehouse_id,
            on_hand_quantity=payload.initial_quantity,
            reorder_point=payload.reorder_point,
            reorder_quantity=payload.reorder_quantity,
        )

        database.add(level)

        if payload.initial_quantity > 0:
            movement = create_inventory_movement(
                database,
                inventory_item_id=item.id,
                warehouse_id=payload.warehouse_id,
                movement_type="initial",
                quantity_change=payload.initial_quantity,
                quantity_before=0,
                quantity_after=payload.initial_quantity,
                source_system="operations-platform",
                notes="Initial inventory quantity",
            )

        database.commit()

    except IntegrityError as exc:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU, barcode, or Shopify identifier already exists",
        ) from exc

    statement = (
        select(InventoryItem)
        .options(selectinload(InventoryItem.inventory_levels))
        .where(InventoryItem.id == item.id)
    )

    return database.scalar(statement)


@router.post(
    "/receiving",
    status_code=status.HTTP_201_CREATED,
)
def receive_inventory(
    payload: ReceivingCreate,
    database: Session = Depends(get_database),
):
    warehouse = database.scalar(
        select(Warehouse).where(
            Warehouse.warehouse_code == payload.warehouse_code,
            Warehouse.is_active.is_(True),
        )
    )

    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found or inactive",
        )

    item = database.scalar(
        select(InventoryItem).where(
            InventoryItem.sku == payload.sku.strip()
        )
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    try:
        level = database.scalar(
            select(InventoryLevel)
            .where(
                InventoryLevel.inventory_item_id == item.id,
                InventoryLevel.warehouse_id == warehouse.id,
            )
            .with_for_update()
        )

        if level is None:
            level = InventoryLevel(
                inventory_item_id=item.id,
                warehouse_id=warehouse.id,
                on_hand_quantity=0,
            )

            database.add(level)
            database.flush()

        quantity_before = level.on_hand_quantity
        quantity_after = quantity_before + payload.quantity

        level.on_hand_quantity = quantity_after

        movement = create_inventory_movement(
            database,
            inventory_item_id=item.id,
            warehouse_id=warehouse.id,
            movement_type="receiving",
            quantity_change=payload.quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reference_type="receiving",
            reference_id=payload.reference_id,
            notes=payload.notes,
            source_system="operations-platform",
        )
        database.commit()
        database.refresh(movement)

        shopify_result = None
        shopify_sync_status = "not_linked"

        if item.shopify_inventory_item_id:
            try:
                shopify_result = push_inventory_to_shopify(
                    item.sku
                )
                shopify_sync_status = "success"

            except Exception as exc:
                shopify_sync_status = "failed"
                shopify_result = {
                    "error": str(exc),
                }

        return {
            "status": "received",
            "movement_id": movement.id,
            "sku": item.sku,
            "name": item.name,
            "warehouse": warehouse.warehouse_code,
            "quantity_received": payload.quantity,
            "quantity_before": quantity_before,
            "quantity_after": quantity_after,
            "shopify_linked":
                item.shopify_inventory_item_id is not None,
            "shopify_sync_status": shopify_sync_status,
            "shopify": shopify_result,
        }

    except Exception:
        database.rollback()
        raise


@router.get(
    "/inventory/{sku}/movements",
    response_model=list[InventoryMovementResponse],
)
def inventory_movement_history(
    sku: str,
    database: Session = Depends(get_database),
):
    item = database.scalar(
        select(InventoryItem).where(
            InventoryItem.sku == sku
        )
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    statement = (
        select(InventoryMovement)
        .where(
            InventoryMovement.inventory_item_id == item.id
        )
        .order_by(InventoryMovement.created_at.desc())
    )

    return database.scalars(statement).all()


@router.post("/shipping")
def ship_inventory(
    payload: ShippingCreate,
    database: Session = Depends(get_database),
):
    warehouse = database.scalar(
        select(Warehouse).where(
            Warehouse.warehouse_code == payload.warehouse_code,
            Warehouse.is_active.is_(True),
        )
    )

    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found or inactive",
        )

    item = database.scalar(
        select(InventoryItem).where(
            InventoryItem.sku == payload.sku.strip()
        )
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    try:
        level = database.scalar(
            select(InventoryLevel)
            .where(
                InventoryLevel.inventory_item_id == item.id,
                InventoryLevel.warehouse_id == warehouse.id,
            )
            .with_for_update()
        )

        if level is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventory level not found",
            )

        quantity_before = level.on_hand_quantity

        if payload.quantity > quantity_before:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Insufficient stock. "
                    f"Requested {payload.quantity}, "
                    f"available {quantity_before}."
                ),
            )

        quantity_after = quantity_before - payload.quantity

        level.on_hand_quantity = quantity_after

        movement = create_inventory_movement(
            database,
            inventory_item_id=item.id,
            warehouse_id=warehouse.id,
            movement_type="shipping",
            quantity_change=-payload.quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reference_type="shipping",
            reference_id=payload.reference_id,
            notes=payload.notes,
            source_system="operations-platform",
        )
        database.commit()
        database.refresh(movement)

        shopify_result = None
        shopify_sync_status = "not_linked"

        if item.shopify_inventory_item_id:
            try:
                shopify_result = push_inventory_to_shopify(
                    item.sku
                )
                shopify_sync_status = "success"

            except Exception as exc:
                shopify_sync_status = "failed"
                shopify_result = {
                    "error": str(exc),
                }

        return {
            "status": "shipped",
            "movement_id": movement.id,
            "sku": item.sku,
            "name": item.name,
            "warehouse": warehouse.warehouse_code,
            "quantity_shipped": payload.quantity,
            "quantity_before": quantity_before,
            "quantity_after": quantity_after,
            "shopify_linked":
                item.shopify_inventory_item_id is not None,
            "shopify_sync_status": shopify_sync_status,
            "shopify": shopify_result,
        }

    except HTTPException:
        database.rollback()
        raise

    except Exception:
        database.rollback()
        raise


@router.post("/inventory-adjustments")
def adjust_inventory(
    payload: InventoryAdjustmentCreate,
    database: Session = Depends(get_database),
):
    allowed_types = {
        "damage",
        "expired",
        "loss",
        "correction",
        "stock_count",
    }

    adjustment_type = payload.adjustment_type.strip().lower()

    if adjustment_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Adjustment type must be one of: "
                "damage, expired, loss, correction, stock_count"
            ),
        )

    warehouse = database.scalar(
        select(Warehouse).where(
            Warehouse.warehouse_code == payload.warehouse_code,
            Warehouse.is_active.is_(True),
        )
    )

    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found or inactive",
        )

    item = database.scalar(
        select(InventoryItem).where(
            InventoryItem.sku == payload.sku.strip()
        )
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    try:
        level = database.scalar(
            select(InventoryLevel)
            .where(
                InventoryLevel.inventory_item_id == item.id,
                InventoryLevel.warehouse_id == warehouse.id,
            )
            .with_for_update()
        )

        if level is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventory level not found",
            )

        quantity_before = level.on_hand_quantity

        if adjustment_type in {
            "damage",
            "expired",
            "loss",
        }:
            if payload.quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Adjustment quantity must be greater than zero",
                )

            if payload.quantity > quantity_before:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Cannot remove {payload.quantity}. "
                        f"Only {quantity_before} units are on hand."
                    ),
                )

            quantity_after = (
                quantity_before - payload.quantity
            )

        else:
            # Correction and stock_count set an exact quantity.
            quantity_after = payload.quantity

        quantity_change = (
            quantity_after - quantity_before
        )

        level.on_hand_quantity = quantity_after

        movement = create_inventory_movement(
            database,
            inventory_item_id=item.id,
            warehouse_id=warehouse.id,
            movement_type=adjustment_type,
            quantity_change=quantity_change,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reference_type="inventory_adjustment",
            reference_id=payload.reference_id,
            notes=payload.notes,
            source_system="operations-platform",
        )
        database.commit()
        database.refresh(movement)

        shopify_result = None
        shopify_sync_status = "not_linked"

        if item.shopify_inventory_item_id:
            try:
                shopify_result = push_inventory_to_shopify(
                    item.sku
                )
                shopify_sync_status = "success"

            except Exception as exc:
                shopify_sync_status = "failed"
                shopify_result = {
                    "error": str(exc),
                }

        return {
            "status": "adjusted",
            "movement_id": movement.id,
            "adjustment_type": adjustment_type,
            "sku": item.sku,
            "name": item.name,
            "warehouse": warehouse.warehouse_code,
            "quantity_change": quantity_change,
            "quantity_before": quantity_before,
            "quantity_after": quantity_after,
            "shopify_sync_status": shopify_sync_status,
            "shopify": shopify_result,
        }

    except HTTPException:
        database.rollback()
        raise

    except Exception:
        database.rollback()
        raise


@router.get("/inventory-movements")
def list_inventory_movements(
    limit: int = 100,
    database: Session = Depends(get_database),
):
    if limit < 1:
        limit = 1

    if limit > 500:
        limit = 500

    statement = (
        select(
            InventoryMovement,
            InventoryItem.sku,
            InventoryItem.name,
            Warehouse.warehouse_code,
        )
        .join(
            InventoryItem,
            InventoryItem.id ==
                InventoryMovement.inventory_item_id,
        )
        .join(
            Warehouse,
            Warehouse.id ==
                InventoryMovement.warehouse_id,
        )
        .order_by(
            InventoryMovement.created_at.desc()
        )
        .limit(limit)
    )

    rows = database.execute(statement).all()

    return [
        {
            "id": movement.id,
            "sku": sku,
            "product_name": name,
            "warehouse": warehouse_code,
            "movement_type":
                movement.movement_type,
            "quantity_change":
                movement.quantity_change,
            "quantity_before":
                movement.quantity_before,
            "quantity_after":
                movement.quantity_after,
            "reference_type":
                movement.reference_type,
            "reference_id":
                movement.reference_id,
            "notes":
                movement.notes,
            "source_system":
                movement.source_system,
            "employee_id":
                movement.employee_id,
            "blockchain_signature":
                movement.blockchain_signature,
            "created_at":
                movement.created_at,
        }
        for (
            movement,
            sku,
            name,
            warehouse_code,
        ) in rows
    ]
