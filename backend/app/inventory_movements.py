from sqlalchemy.orm import Session

from app.models import InventoryMovement


def create_inventory_movement(
    database: Session,
    *,
    inventory_item_id: int,
    warehouse_id: int,
    movement_type: str,
    quantity_change: int,
    quantity_before: int,
    quantity_after: int,
    reference_type: str | None = None,
    reference_id: str | None = None,
    notes: str | None = None,
    source_system: str = "operations-platform",
    employee_id: int | None = None,
) -> InventoryMovement:
    """
    Create and flush an inventory movement.

    The caller still controls the database transaction and decides
    when to commit or roll back.

    flush() assigns the movement ID without committing the surrounding
    operational transaction.
    """

    movement = InventoryMovement(
        inventory_item_id=inventory_item_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        quantity_change=quantity_change,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        source_system=source_system,
        employee_id=employee_id,
    )

    database.add(movement)
    database.flush()

    return movement
