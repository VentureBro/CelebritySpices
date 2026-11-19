from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import SessionLocal
from app.inventory_movements import create_inventory_movement
from app.models import Order


router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


def get_database():
    database = SessionLocal()

    try:
        yield database
    finally:
        database.close()


@router.get("")
def list_orders(
    database: Session = Depends(get_database),
):
    statement = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.shopify_created_at.desc())
    )

    orders = database.scalars(statement).all()

    return [
        {
            "id": order.id,
            "shopify_order_id": order.shopify_order_id,
            "shopify_order_name": order.shopify_order_name,
            "financial_status": order.financial_status,
            "fulfillment_status": order.fulfillment_status,
            "customer_name": order.customer_name,
            "operational_status": order.operational_status,
            "shopify_created_at": order.shopify_created_at,
            "imported_at": order.imported_at,
            "items": [
                {
                    "id": item.id,
                    "shopify_line_item_id":
                        item.shopify_line_item_id,
                    "sku": item.sku,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "current_quantity":
                        item.current_quantity,
                    "shopify_variant_id":
                        item.shopify_variant_id,
                    "inventory_item_id":
                        item.inventory_item_id,
                }
                for item in order.items
            ],
        }
        for order in orders
    ]


@router.get("/{order_id}")
def get_order(
    order_id: int,
    database: Session = Depends(get_database),
):
    statement = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )

    order = database.scalar(statement)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return {
        "id": order.id,
        "shopify_order_id": order.shopify_order_id,
        "shopify_order_name": order.shopify_order_name,
        "financial_status": order.financial_status,
        "fulfillment_status": order.fulfillment_status,
        "customer_name": order.customer_name,
        "operational_status": order.operational_status,
        "shopify_created_at": order.shopify_created_at,
        "imported_at": order.imported_at,
        "items": [
            {
                "id": item.id,
                "sku": item.sku,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "current_quantity": item.current_quantity,
                "inventory_item_id": item.inventory_item_id,
            }
            for item in order.items
        ],
    }


@router.post("/{order_id}/reserve")
def reserve_order(
    order_id: int,
    database: Session = Depends(get_database),
):
    from app.models import (
        InventoryLevel,
        InventoryMovement,
        OrderItem,
        Warehouse,
    )

    order = database.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.operational_status == "reserved":
        return {
            "status": "already_reserved",
            "order_id": order.id,
            "order": order.shopify_order_name,
        }

    warehouse = database.scalar(
        select(Warehouse).where(
            Warehouse.warehouse_code == "MAIN",
            Warehouse.is_active.is_(True),
        )
    )

    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MAIN warehouse not found or inactive",
        )

    try:
        reservations = []

        for order_item in order.items:
            if order_item.current_quantity <= 0:
                continue

            if order_item.inventory_item_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Order item {order_item.product_name} "
                        "is not linked to local inventory"
                    ),
                )

            level = database.scalar(
                select(InventoryLevel)
                .where(
                    InventoryLevel.inventory_item_id ==
                        order_item.inventory_item_id,
                    InventoryLevel.warehouse_id ==
                        warehouse.id,
                )
                .with_for_update()
            )

            if level is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        f"Inventory level missing for "
                        f"{order_item.sku}"
                    ),
                )

            available_local = (
                level.on_hand_quantity
                - level.committed_quantity
                - level.reserved_quantity
            )

            quantity_needed = order_item.current_quantity

            if quantity_needed > available_local:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Insufficient available stock for "
                        f"{order_item.sku}. "
                        f"Needed {quantity_needed}, "
                        f"available {available_local}."
                    ),
                )

            committed_before = level.committed_quantity
            committed_after = (
                committed_before + quantity_needed
            )

            level.committed_quantity = committed_after

            create_inventory_movement(
                database,
                inventory_item_id=
                    order_item.inventory_item_id,
                warehouse_id=warehouse.id,
                movement_type="sale",
                quantity_change=0,
                quantity_before=
                    level.on_hand_quantity,
                quantity_after=
                    level.on_hand_quantity,
                reference_type="order_reservation",
                reference_id=
                    order.shopify_order_name,
                notes=(
                    f"Committed {quantity_needed} unit(s) "
                    f"to Shopify order "
                    f"{order.shopify_order_name}"
                ),
                source_system="shopify",
            )

            reservations.append({
                "sku": order_item.sku,
                "quantity": quantity_needed,
                "on_hand": level.on_hand_quantity,
                "committed_before": committed_before,
                "committed_after": committed_after,
                "available_after": (
                    level.on_hand_quantity
                    - committed_after
                    - level.reserved_quantity
                ),
            })

        order.operational_status = "reserved"

        database.commit()

        return {
            "status": "reserved",
            "order_id": order.id,
            "order": order.shopify_order_name,
            "items": reservations,
        }

    except HTTPException:
        database.rollback()
        raise

    except Exception:
        database.rollback()
        raise


@router.post("/{order_id}/ship")
def ship_order(
    order_id: int,
    database: Session = Depends(get_database),
):
    from app.models import (
        InventoryLevel,
        Warehouse,
    )

    order = database.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.operational_status == "shipped":
        return {
            "status": "already_shipped",
            "order_id": order.id,
            "order": order.shopify_order_name,
        }

    if order.operational_status != "reserved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order must be reserved before shipping",
        )

    warehouse = database.scalar(
        select(Warehouse).where(
            Warehouse.warehouse_code == "MAIN",
            Warehouse.is_active.is_(True),
        )
    )

    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MAIN warehouse not found or inactive",
        )

    try:
        shipments = []

        for order_item in order.items:
            quantity_to_ship = order_item.current_quantity

            if quantity_to_ship <= 0:
                continue

            if order_item.inventory_item_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Order item {order_item.product_name} "
                        "is not linked to local inventory"
                    ),
                )

            level = database.scalar(
                select(InventoryLevel)
                .where(
                    InventoryLevel.inventory_item_id ==
                        order_item.inventory_item_id,
                    InventoryLevel.warehouse_id ==
                        warehouse.id,
                )
                .with_for_update()
            )

            if level is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Inventory level missing for {order_item.sku}",
                )

            if quantity_to_ship > level.committed_quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Committed stock too low for {order_item.sku}. "
                        f"Need {quantity_to_ship}, "
                        f"committed {level.committed_quantity}."
                    ),
                )

            if quantity_to_ship > level.on_hand_quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Physical stock too low for {order_item.sku}. "
                        f"Need {quantity_to_ship}, "
                        f"on hand {level.on_hand_quantity}."
                    ),
                )

            on_hand_before = level.on_hand_quantity
            committed_before = level.committed_quantity

            level.on_hand_quantity = (
                on_hand_before - quantity_to_ship
            )

            level.committed_quantity = (
                committed_before - quantity_to_ship
            )

            create_inventory_movement(
                database,
                inventory_item_id=
                    order_item.inventory_item_id,
                warehouse_id=warehouse.id,
                movement_type="shipping",
                quantity_change=-quantity_to_ship,
                quantity_before=on_hand_before,
                quantity_after=level.on_hand_quantity,
                reference_type="order_shipping",
                reference_id=order.shopify_order_name,
                notes=(
                    f"Shipped {quantity_to_ship} unit(s) "
                    f"for Shopify order "
                    f"{order.shopify_order_name}"
                ),
                source_system="operations-platform",
            )

            shipments.append({
                "sku": order_item.sku,
                "quantity": quantity_to_ship,
                "on_hand_before": on_hand_before,
                "on_hand_after": level.on_hand_quantity,
                "committed_before": committed_before,
                "committed_after": level.committed_quantity,
                "available_after": (
                    level.on_hand_quantity
                    - level.committed_quantity
                    - level.reserved_quantity
                ),
            })

        order.operational_status = "shipped"

        database.commit()

        return {
            "status": "shipped",
            "order_id": order.id,
            "order": order.shopify_order_name,
            "items": shipments,
        }

    except HTTPException:
        database.rollback()
        raise

    except Exception:
        database.rollback()
        raise
