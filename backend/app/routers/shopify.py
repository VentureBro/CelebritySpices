from fastapi import APIRouter, HTTPException

from app.shopify import shopify_graphql
from app.inventory_movements import create_inventory_movement


router = APIRouter(
    prefix="/shopify",
    tags=["Shopify"],
)


@router.get("/health")
def shopify_health():
    query = """
    query {
      shop {
        name
        myshopifyDomain
      }
    }
    """

    try:
        data = shopify_graphql(query)

        return {
            "status": "connected",
            "shop": data["shop"],
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/products")
def shopify_products():
    query = """
    query {
      products(first: 25) {
        nodes {
          id
          title
          status

          variants(first: 100) {
            nodes {
              id
              title
              sku
              barcode

              inventoryItem {
                id
                tracked
              }
            }
          }
        }
      }
    }
    """

    try:
        return shopify_graphql(query)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/locations")
def shopify_locations():
    query = """
    query {
      locations(first: 50) {
        nodes {
          id
          name
          isActive
        }
      }
    }
    """

    try:
        return shopify_graphql(query)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/inventory-preview")
def shopify_inventory_preview():
    query = """
    query InventoryPreview($locationId: ID!) {
      products(first: 100) {
        nodes {
          id
          title
          status

          variants(first: 100) {
            nodes {
              id
              title
              sku
              barcode

              inventoryItem {
                id
                tracked

                inventoryLevel(locationId: $locationId) {
                  id
                  isActive

                  quantities(
                    names: [
                      "available",
                      "on_hand",
                      "incoming",
                      "committed"
                    ]
                  ) {
                    name
                    quantity
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    location_id = "gid://shopify/Location/88760778972"

    try:
        data = shopify_graphql(
            query,
            {"locationId": location_id},
        )

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    items = []

    for product in data["products"]["nodes"]:
        for variant in product["variants"]["nodes"]:
            inventory_item = variant["inventoryItem"]
            inventory_level = inventory_item.get("inventoryLevel")

            quantities = {}

            if inventory_level:
                quantities = {
                    quantity["name"]: quantity["quantity"]
                    for quantity in inventory_level["quantities"]
                }

            items.append(
                {
                    "product": product["title"],
                    "product_status": product["status"],
                    "sku": variant.get("sku"),
                    "shopify_product_id": product["id"],
                    "shopify_variant_id": variant["id"],
                    "shopify_inventory_item_id": inventory_item["id"],
                    "tracked": inventory_item["tracked"],
                    "inventory_level_active": (
                        inventory_level["isActive"]
                        if inventory_level
                        else False
                    ),
                    "available": quantities.get("available", 0),
                    "on_hand": quantities.get("on_hand", 0),
                    "incoming": quantities.get("incoming", 0),
                    "committed": quantities.get("committed", 0),
                }
            )

    return {
        "location_id": location_id,
        "count": len(items),
        "items": items,
    }


@router.post("/import-products")
def import_shopify_products():
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import InventoryItem, InventoryLevel, Warehouse

    query = """
    query {
      products(first: 100) {
        nodes {
          id
          title
          status

          variants(first: 100) {
            nodes {
              id
              title
              sku
              barcode

              inventoryItem {
                id
                tracked
              }
            }
          }
        }
      }
    }
    """

    try:
        data = shopify_graphql(query)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    database = SessionLocal()

    created = []
    updated = []
    skipped = []

    try:
        warehouse = database.scalar(
            select(Warehouse).where(
                Warehouse.warehouse_code == "MAIN"
            )
        )

        if warehouse is None:
            raise HTTPException(
                status_code=500,
                detail="MAIN warehouse does not exist",
            )

        now = datetime.now(timezone.utc)

        for product in data["products"]["nodes"]:
            for variant in product["variants"]["nodes"]:

                sku = (variant.get("sku") or "").strip()

                if not sku:
                    skipped.append(
                        {
                            "product": product["title"],
                            "reason": "No SKU",
                        }
                    )
                    continue

                inventory_item = variant["inventoryItem"]

                existing = database.scalar(
                    select(InventoryItem).where(
                        InventoryItem.sku == sku
                    )
                )

                if existing is not None:
                    existing.shopify_product_id = product["id"]
                    existing.shopify_variant_id = variant["id"]
                    existing.shopify_inventory_item_id = (
                        inventory_item["id"]
                    )
                    existing.barcode = (
                        variant.get("barcode") or existing.barcode
                    )
                    existing.tracks_inventory = inventory_item["tracked"]
                    existing.last_shopify_sync_at = now

                    updated.append(
                        {
                            "sku": sku,
                            "product": product["title"],
                            "local_inventory_id": existing.id,
                            "quantity_preserved": True,
                        }
                    )

                    continue

                item = InventoryItem(
                    sku=sku,
                    name=product["title"],
                    barcode=variant.get("barcode"),
                    unit_of_measure="each",
                    shopify_product_id=product["id"],
                    shopify_variant_id=variant["id"],
                    shopify_inventory_item_id=inventory_item["id"],
                    tracks_inventory=inventory_item["tracked"],
                    is_active=True,
                    last_shopify_sync_at=now,
                )

                database.add(item)
                database.flush()

                level = InventoryLevel(
                    inventory_item_id=item.id,
                    warehouse_id=warehouse.id,
                    on_hand_quantity=0,
                    committed_quantity=0,
                    incoming_quantity=0,
                    reserved_quantity=0,
                    reorder_point=0,
                    reorder_quantity=0,
                    last_shopify_sync_at=now,
                )

                database.add(level)

                created.append(
                    {
                        "sku": sku,
                        "product": product["title"],
                        "local_inventory_id": item.id,
                        "initial_local_quantity": 0,
                    }
                )

        database.commit()

        return {
            "status": "completed",
            "created_count": len(created),
            "updated_count": len(updated),
            "skipped_count": len(skipped),
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }

    except HTTPException:
        database.rollback()
        raise

    except Exception as exc:
        database.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {exc}",
        ) from exc

    finally:
        database.close()


@router.post("/sync-products")
def sync_shopify_products():
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import InventoryItem

    query = """
    query {
      products(first: 100) {
        nodes {
          id
          title
          variants(first: 100) {
            nodes {
              id
              sku
              inventoryItem {
                id
              }
            }
          }
        }
      }
    }
    """

    try:
        data = shopify_graphql(query)

        database = SessionLocal()

        matched = []
        skipped = []

        try:
            for product in data["products"]["nodes"]:
                for variant in product["variants"]["nodes"]:

                    sku = variant.get("sku")

                    if not sku:
                        skipped.append({
                            "product": product["title"],
                            "reason": "No SKU"
                        })
                        continue

                    statement = select(InventoryItem).where(
                        InventoryItem.sku == sku
                    )

                    item = database.scalar(statement)

                    if item is None:
                        skipped.append({
                            "product": product["title"],
                            "sku": sku,
                            "reason": "No matching local SKU"
                        })
                        continue

                    item.shopify_product_id = product["id"]
                    item.shopify_variant_id = variant["id"]
                    item.shopify_inventory_item_id = (
                        variant["inventoryItem"]["id"]
                        if variant.get("inventoryItem")
                        else None
                    )

                    matched.append({
                        "sku": sku,
                        "product": product["title"],
                        "local_inventory_id": item.id,
                        "shopify_product_id": product["id"],
                        "shopify_variant_id": variant["id"],
                        "shopify_inventory_item_id":
                            item.shopify_inventory_item_id
                    })

            database.commit()

        finally:
            database.close()

        return {
            "status": "completed",
            "matched_count": len(matched),
            "skipped_count": len(skipped),
            "matched": matched,
            "skipped": skipped
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/inventory-comparison")
def shopify_inventory_comparison():
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import InventoryItem, InventoryLevel, Warehouse

    database = SessionLocal()

    try:
        warehouse = database.scalar(
            select(Warehouse).where(Warehouse.warehouse_code == "MAIN")
        )

        if warehouse is None or not warehouse.shopify_location_id:
            raise HTTPException(
                status_code=500,
                detail="MAIN warehouse is not linked to a Shopify location",
            )

        items = database.scalars(
            select(InventoryItem)
            .where(InventoryItem.shopify_inventory_item_id.is_not(None))
            .order_by(InventoryItem.sku)
        ).all()

        results = []

        for item in items:
            level = database.scalar(
                select(InventoryLevel).where(
                    InventoryLevel.inventory_item_id == item.id,
                    InventoryLevel.warehouse_id == warehouse.id,
                )
            )

            query = """
            query InventoryItem($id: ID!) {
              inventoryItem(id: $id) {
                id
                sku
                inventoryLevels(first: 50) {
                  nodes {
                    location {
                      id
                      name
                    }
                    quantities(names: ["available"]) {
                      name
                      quantity
                    }
                  }
                }
              }
            }
            """

            data = shopify_graphql(
                query,
                {"id": item.shopify_inventory_item_id},
            )

            shopify_quantity = None
            shopify_location_name = None

            inventory_item = data.get("inventoryItem")

            if inventory_item:
                for shopify_level in inventory_item["inventoryLevels"]["nodes"]:
                    location = shopify_level["location"]

                    if location["id"] == warehouse.shopify_location_id:
                        shopify_location_name = location["name"]

                        for quantity in shopify_level["quantities"]:
                            if quantity["name"] == "available":
                                shopify_quantity = quantity["quantity"]
                                break

                        break

            local_on_hand = (
                level.on_hand_quantity
                if level
                else 0
            )

            local_committed = (
                level.committed_quantity
                if level
                else 0
            )

            local_reserved = (
                level.reserved_quantity
                if level
                else 0
            )

            local_available = (
                local_on_hand
                - local_committed
                - local_reserved
            )

            difference = (
                local_available - shopify_quantity
                if shopify_quantity is not None
                else None
            )

            if shopify_quantity is None:
                sync_status = "not_stocked_at_location"
            elif difference == 0:
                sync_status = "matched"
            else:
                sync_status = "different"

            results.append(
                {
                    "sku": item.sku,
                    "name": item.name,
                    "local_on_hand": local_on_hand,
                    "local_committed": local_committed,
                    "local_reserved": local_reserved,
                    "local_available": local_available,
                    "shopify_available": shopify_quantity,
                    "difference": difference,
                    "status": sync_status,
                    "shopify_location": shopify_location_name,
                }
            )

        return {
            "warehouse": warehouse.warehouse_code,
            "shopify_location_id": warehouse.shopify_location_id,
            "count": len(results),
            "items": results,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    finally:
        database.close()


@router.post("/sync-inventory-from-shopify")
def sync_inventory_from_shopify():
    from datetime import datetime, timezone
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import (
        InventoryItem,
        InventoryLevel,
        Warehouse,
    )

    database = SessionLocal()

    try:
        warehouse = database.scalar(
            select(Warehouse).where(
                Warehouse.warehouse_code == "MAIN"
            )
        )

        if warehouse is None or not warehouse.shopify_location_id:
            raise HTTPException(
                status_code=500,
                detail="MAIN warehouse is not linked to Shopify",
            )

        items = database.scalars(
            select(InventoryItem)
            .where(
                InventoryItem.shopify_inventory_item_id.is_not(None)
            )
            .order_by(InventoryItem.sku)
        ).all()

        updated = []
        unchanged = []
        skipped = []

        for item in items:
            query = """
            query InventoryItem($id: ID!) {
              inventoryItem(id: $id) {
                id
                sku
                inventoryLevels(first: 50) {
                  nodes {
                    location {
                      id
                      name
                    }
                    quantities(names: ["on_hand", "available"]) {
                      name
                      quantity
                    }
                  }
                }
              }
            }
            """

            data = shopify_graphql(
                query,
                {"id": item.shopify_inventory_item_id},
            )

            inventory_item = data.get("inventoryItem")

            if not inventory_item:
                skipped.append({
                    "sku": item.sku,
                    "reason": "Shopify inventory item not found",
                })
                continue

            shopify_on_hand = None
            shopify_available = None
            shopify_location_name = None

            for shopify_level in inventory_item[
                "inventoryLevels"
            ]["nodes"]:

                location = shopify_level["location"]

                if location["id"] != warehouse.shopify_location_id:
                    continue

                shopify_location_name = location["name"]

                for quantity in shopify_level["quantities"]:
                    if quantity["name"] == "on_hand":
                        shopify_on_hand = quantity["quantity"]

                    if quantity["name"] == "available":
                        shopify_available = quantity["quantity"]

                break

            if shopify_on_hand is None:
                skipped.append({
                    "sku": item.sku,
                    "reason": "Not stocked at linked Shopify location",
                })
                continue

            level = database.scalar(
                select(InventoryLevel).where(
                    InventoryLevel.inventory_item_id == item.id,
                    InventoryLevel.warehouse_id == warehouse.id,
                )
            )

            if level is None:
                level = InventoryLevel(
                    inventory_item_id=item.id,
                    warehouse_id=warehouse.id,
                    on_hand_quantity=0,
                )
                database.add(level)
                database.flush()

            before = level.on_hand_quantity
            after = shopify_on_hand

            level.on_hand_quantity = after
            level.shopify_available_quantity = shopify_available
            level.last_shopify_sync_at = datetime.now(timezone.utc)

            item.last_shopify_sync_at = datetime.now(timezone.utc)

            if before != after:
                create_inventory_movement(
                    database,
                    inventory_item_id=item.id,
                    warehouse_id=warehouse.id,
                    movement_type="shopify_sync",
                    quantity_change=after - before,
                    quantity_before=before,
                    quantity_after=after,
                    source_system="shopify",
                    notes=(
                        "Initial/controlled inventory synchronization "
                        "from Shopify"
                    ),
                )

                updated.append({
                    "sku": item.sku,
                    "name": item.name,
                    "before": before,
                    "after": after,
                    "shopify_available": shopify_available,
                    "location": shopify_location_name,
                })

            else:
                unchanged.append({
                    "sku": item.sku,
                    "quantity": after,
                    "shopify_available": shopify_available,
                })

        database.commit()

        return {
            "status": "completed",
            "updated_count": len(updated),
            "unchanged_count": len(unchanged),
            "skipped_count": len(skipped),
            "updated": updated,
            "unchanged": unchanged,
            "skipped": skipped,
        }

    except HTTPException:
        database.rollback()
        raise

    except Exception as exc:
        database.rollback()

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    finally:
        database.close()


@router.post("/push-inventory/{sku}")
def push_inventory_to_shopify(sku: str):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import (
        InventoryItem,
        InventoryLevel,
        Warehouse,
    )

    database = SessionLocal()

    try:
        warehouse = database.scalar(
            select(Warehouse).where(
                Warehouse.warehouse_code == "MAIN"
            )
        )

        if warehouse is None or not warehouse.shopify_location_id:
            raise HTTPException(
                status_code=500,
                detail="MAIN warehouse is not linked to Shopify",
            )

        item = database.scalar(
            select(InventoryItem).where(
                InventoryItem.sku == sku
            )
        )

        if item is None:
            raise HTTPException(
                status_code=404,
                detail="Local inventory item not found",
            )

        if not item.shopify_inventory_item_id:
            raise HTTPException(
                status_code=400,
                detail="Inventory item is not linked to Shopify",
            )

        level = database.scalar(
            select(InventoryLevel).where(
                InventoryLevel.inventory_item_id == item.id,
                InventoryLevel.warehouse_id == warehouse.id,
            )
        )

        if level is None:
            raise HTTPException(
                status_code=404,
                detail="Local inventory level not found",
            )

        query = """
        query InventoryItem($id: ID!) {
          inventoryItem(id: $id) {
            id
            inventoryLevels(first: 50) {
              nodes {
                location {
                  id
                  name
                }
                quantities(names: ["available"]) {
                  name
                  quantity
                }
              }
            }
          }
        }
        """

        data = shopify_graphql(
            query,
            {"id": item.shopify_inventory_item_id},
        )

        shopify_before = None

        inventory_item = data.get("inventoryItem")

        if inventory_item:
            for shopify_level in inventory_item[
                "inventoryLevels"
            ]["nodes"]:

                if (
                    shopify_level["location"]["id"]
                    != warehouse.shopify_location_id
                ):
                    continue

                for quantity in shopify_level["quantities"]:
                    if quantity["name"] == "available":
                        shopify_before = quantity["quantity"]
                        break

                break

        if shopify_before is None:
            raise HTTPException(
                status_code=400,
                detail="Shopify inventory level not found at linked location",
            )

        target_quantity = (
            level.on_hand_quantity
            - level.committed_quantity
            - level.reserved_quantity
        )

        if target_quantity < 0:
            raise HTTPException(
                status_code=409,
                detail="Local available inventory cannot be negative",
            )

        delta = target_quantity - shopify_before

        if delta == 0:
            return {
                "status": "unchanged",
                "sku": sku,
                "local_quantity": target_quantity,
                "shopify_quantity": shopify_before,
                "message": "Shopify already matches local inventory",
            }

        mutation = """
        mutation InventoryAdjustQuantities(
          $input: InventoryAdjustQuantitiesInput!,
          $idempotencyKey: String!
        ) {
          inventoryAdjustQuantities(input: $input)
            @idempotent(key: $idempotencyKey) {
            inventoryAdjustmentGroup {
              createdAt
              reason
            }
            userErrors {
              field
              message
            }
          }
        }
        """

        import uuid

        variables = {
            "idempotencyKey": str(uuid.uuid4()),
            "input": {
                "name": "available",
                "reason": "correction",
                "changes": [
                    {
                        "delta": delta,
                        "changeFromQuantity": shopify_before,
                        "inventoryItemId":
                            item.shopify_inventory_item_id,
                        "locationId":
                            warehouse.shopify_location_id,
                    }
                ],
            }
        }

        result = shopify_graphql(
            mutation,
            variables,
        )

        payload = result["inventoryAdjustQuantities"]
        errors = payload.get("userErrors", [])

        if errors:
            raise HTTPException(
                status_code=400,
                detail=errors,
            )

        level.shopify_available_quantity = target_quantity

        create_inventory_movement(
            database,
            inventory_item_id=item.id,
            warehouse_id=warehouse.id,
            movement_type="shopify_sync",
            quantity_change=delta,
            quantity_before=shopify_before,
            quantity_after=target_quantity,
            source_system="operations-platform",
            notes="Manual Local to Shopify inventory push",
        )

        database.commit()

        return {
            "status": "updated",
            "sku": sku,
            "shopify_before": shopify_before,
            "local_quantity": target_quantity,
            "delta_sent": delta,
            "shopify_after_expected": target_quantity,
        }

    except HTTPException:
        database.rollback()
        raise

    except Exception as exc:
        database.rollback()

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    finally:
        database.close()


@router.get("/orders")
def shopify_orders():
    query = """
    query {
      orders(
        first: 25
        sortKey: CREATED_AT
        reverse: true
      ) {
        nodes {
          id
          name
          createdAt
          displayFinancialStatus
          displayFulfillmentStatus

          lineItems(first: 100) {
            nodes {
              id
              name
              sku
              quantity
              currentQuantity

              variant {
                id
              }
            }
          }
        }
      }
    }
    """

    try:
        return shopify_graphql(query)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.post("/import-orders")
def import_shopify_orders():
    from datetime import datetime
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import (
        InventoryItem,
        Order,
        OrderItem,
    )

    query = """
    query {
      orders(
        first: 50
        sortKey: CREATED_AT
        reverse: true
      ) {
        nodes {
          id
          name
          createdAt
          displayFinancialStatus
          displayFulfillmentStatus

          lineItems(first: 100) {
            nodes {
              id
              name
              sku
              quantity
              currentQuantity

              variant {
                id
              }
            }
          }
        }
      }
    }
    """

    database = SessionLocal()

    try:
        data = shopify_graphql(query)

        imported = []
        updated = []
        unmatched_items = []

        for shopify_order in data["orders"]["nodes"]:
            order = database.scalar(
                select(Order).where(
                    Order.shopify_order_id ==
                        shopify_order["id"]
                )
            )

            created_at = datetime.fromisoformat(
                shopify_order["createdAt"].replace(
                    "Z",
                    "+00:00",
                )
            )

            if order is None:
                order = Order(
                    shopify_order_id=shopify_order["id"],
                    shopify_order_name=shopify_order["name"],
                    financial_status=
                        shopify_order[
                            "displayFinancialStatus"
                        ],
                    fulfillment_status=
                        shopify_order[
                            "displayFulfillmentStatus"
                        ],
                    customer_name=None,
                    operational_status="new",
                    shopify_created_at=created_at,
                )

                database.add(order)
                database.flush()

                imported.append(
                    shopify_order["name"]
                )

            else:
                order.financial_status = (
                    shopify_order[
                        "displayFinancialStatus"
                    ]
                )
                order.fulfillment_status = (
                    shopify_order[
                        "displayFulfillmentStatus"
                    ]
                )
                order.customer_name = None

                updated.append(
                    shopify_order["name"]
                )

            for line in shopify_order[
                "lineItems"
            ]["nodes"]:

                order_item = database.scalar(
                    select(OrderItem).where(
                        OrderItem.shopify_line_item_id ==
                            line["id"]
                    )
                )

                inventory_item = None

                sku = line.get("sku")

                if sku:
                    inventory_item = database.scalar(
                        select(InventoryItem).where(
                            InventoryItem.sku == sku
                        )
                    )

                if order_item is None:
                    order_item = OrderItem(
                        order_id=order.id,
                        shopify_line_item_id=line["id"],
                        sku=sku,
                        product_name=line["name"],
                        quantity=line["quantity"],
                        current_quantity=
                            line["currentQuantity"],
                        shopify_variant_id=(
                            line["variant"]["id"]
                            if line.get("variant")
                            else None
                        ),
                        inventory_item_id=(
                            inventory_item.id
                            if inventory_item
                            else None
                        ),
                    )

                    database.add(order_item)

                else:
                    order_item.sku = sku
                    order_item.product_name = line["name"]
                    order_item.quantity = line["quantity"]
                    order_item.current_quantity = (
                        line["currentQuantity"]
                    )
                    order_item.shopify_variant_id = (
                        line["variant"]["id"]
                        if line.get("variant")
                        else None
                    )
                    order_item.inventory_item_id = (
                        inventory_item.id
                        if inventory_item
                        else None
                    )

                if sku and inventory_item is None:
                    unmatched_items.append({
                        "order": shopify_order["name"],
                        "sku": sku,
                        "product": line["name"],
                    })

        database.commit()

        return {
            "status": "completed",
            "imported_count": len(imported),
            "updated_count": len(updated),
            "unmatched_item_count":
                len(unmatched_items),
            "imported": imported,
            "updated": updated,
            "unmatched_items": unmatched_items,
        }

    except Exception as exc:
        database.rollback()

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    finally:
        database.close()


@router.get("/orders/{order_id:path}/fulfillment-orders")
def shopify_order_fulfillment_orders(order_id: str):
    query = """
    query FulfillmentOrderList($orderId: ID!) {
      order(id: $orderId) {
        id
        name

        fulfillmentOrders(first: 50) {
          nodes {
            id
            status
            requestStatus

            assignedLocation {
              name
              location {
                id
              }
            }

            lineItems(first: 100) {
              nodes {
                id
                totalQuantity
                remainingQuantity

                variant {
                  id
                }
              }
            }
          }
        }
      }
    }
    """

    try:
        return shopify_graphql(
            query,
            {"orderId": order_id},
        )

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/scopes")
def shopify_scopes():
    query = """
    query {
      currentAppInstallation {
        accessScopes {
          handle
        }
      }
    }
    """

    try:
        return shopify_graphql(query)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/scopes")
def shopify_scopes():
    query = """
    query {
      currentAppInstallation {
        accessScopes {
          handle
        }
      }
    }
    """

    try:
        return shopify_graphql(query)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
