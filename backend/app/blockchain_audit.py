import hashlib
import json
from datetime import timezone

from app.models import InventoryMovement


AUDIT_FIELDS = (
    "created_at",
    "id",
    "inventory_item_id",
    "movement_type",
    "notes",
    "quantity_after",
    "quantity_before",
    "quantity_change",
    "reference_id",
    "reference_type",
    "source_system",
    "warehouse_id",
)


def canonical_created_at(value) -> str:
    if value is None:
        raise ValueError("Inventory movement created_at is missing.")

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)

    return (
        value.isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def inventory_audit_payload(
    movement: InventoryMovement,
) -> dict:
    return {
        "created_at": canonical_created_at(
            movement.created_at
        ),
        "id": movement.id,
        "inventory_item_id": movement.inventory_item_id,
        "movement_type": movement.movement_type,
        "notes": movement.notes,
        "quantity_after": movement.quantity_after,
        "quantity_before": movement.quantity_before,
        "quantity_change": movement.quantity_change,
        "reference_id": movement.reference_id,
        "reference_type": movement.reference_type,
        "source_system": movement.source_system,
        "warehouse_id": movement.warehouse_id,
    }


def canonical_inventory_audit_json(
    movement: InventoryMovement,
) -> str:
    payload = inventory_audit_payload(movement)

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def inventory_audit_hash(
    movement: InventoryMovement,
) -> bytes:
    canonical_json = canonical_inventory_audit_json(
        movement
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).digest()


def inventory_audit_hash_hex(
    movement: InventoryMovement,
) -> str:
    return inventory_audit_hash(movement).hex()
