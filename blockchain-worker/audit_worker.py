import hashlib
import json
import os
from datetime import timezone
from pathlib import Path

import psycopg
from solders.pubkey import Pubkey


PROGRAM_ID = Pubkey.from_string(
    "Af1raDw63K9whsXG6CGUBxcpGmSLQf8jzEcEay3zLT4z"
)


def canonical_created_at(value) -> str:
    if value is None:
        raise ValueError("created_at is missing")

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)

    return value.isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def canonical_payload(row: dict) -> dict:
    return {
        "created_at": canonical_created_at(
            row["created_at"]
        ),
        "id": row["id"],
        "inventory_item_id": row[
            "inventory_item_id"
        ],
        "movement_type": row["movement_type"],
        "notes": row["notes"],
        "quantity_after": row["quantity_after"],
        "quantity_before": row[
            "quantity_before"
        ],
        "quantity_change": row[
            "quantity_change"
        ],
        "reference_id": row["reference_id"],
        "reference_type": row[
            "reference_type"
        ],
        "source_system": row["source_system"],
        "warehouse_id": row["warehouse_id"],
    }


def canonical_json(row: dict) -> str:
    return json.dumps(
        canonical_payload(row),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def audit_hash(row: dict) -> bytes:
    return hashlib.sha256(
        canonical_json(row).encode("utf-8")
    ).digest()


def audit_pda(movement_id: int):
    seed = movement_id.to_bytes(
        8,
        byteorder="little",
        signed=False,
    )

    return Pubkey.find_program_address(
        [
            b"inventory-audit",
            seed,
        ],
        PROGRAM_ID,
    )


def database_connection():
    return psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=psycopg.rows.dict_row,
    )


def load_movement(movement_id: int):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    inventory_item_id,
                    warehouse_id,
                    movement_type,
                    quantity_change,
                    quantity_before,
                    quantity_after,
                    reference_type,
                    reference_id,
                    notes,
                    source_system,
                    blockchain_signature,
                    created_at
                FROM inventory_movements
                WHERE id = %s
                """,
                (movement_id,),
            )

            row = cur.fetchone()

    if row is None:
        raise RuntimeError(
            f"Movement {movement_id} not found"
        )

    return row


def main():
    movement = load_movement(30)

    canonical = canonical_json(movement)
    digest = audit_hash(movement)
    pda, bump = audit_pda(movement["id"])

    print(
        "===== BLOCKCHAIN AUDIT WORKER TEST ====="
    )
    print("Movement:", movement["id"])
    print(
        "Inventory item:",
        movement["inventory_item_id"],
    )
    print(
        "Quantity:",
        f'{movement["quantity_before"]}'
        f' -> {movement["quantity_after"]}',
    )

    print()
    print("===== CANONICAL JSON =====")
    print(canonical)

    print()
    print("===== SHA-256 =====")
    print(digest.hex())

    print()
    print("===== PDA =====")
    print(pda)
    print("Bump:", bump)

    print()
    print("===== DATABASE SIGNATURE =====")
    print(movement["blockchain_signature"])


if __name__ == "__main__":
    main()
