import base64
import hashlib
import json
import os
import struct
import sys
import time
import urllib.request
from datetime import timezone
from pathlib import Path

import psycopg
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction


RPC_URL = "http://127.0.0.1:8899"

PROGRAM_ID = Pubkey.from_string(
    "Af1raDw63K9whsXG6CGUBxcpGmSLQf8jzEcEay3zLT4z"
)

SYSTEM_PROGRAM = Pubkey.from_string(
    "11111111111111111111111111111111"
)

ANCHOR_DISCRIMINATOR = bytes([
    133, 236, 129, 214,
    222, 66, 139, 144,
])

INVENTORY_AUDIT_DISCRIMINATOR = bytes([
    116, 39, 50, 148,
    79, 171, 153, 45,
])

KEYPAIR_PATH = Path(
    "../secrets/solana-audit-authority.json"
)


def rpc(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }

    if params is not None:
        payload["params"] = params

    request = urllib.request.Request(
        RPC_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=15,
    ) as response:
        result = json.loads(
            response.read().decode()
        )

    if "error" in result:
        raise RuntimeError(
            json.dumps(result["error"])
        )

    return result["result"]


def database_connection():
    if os.environ.get("CELEBRITYSPICES_DEV_DB_ALLOWED") != "1" or not os.environ.get("POSTGRES_DB", "").endswith("_dev"):
        raise RuntimeError("Development database connection blocked: explicit authorization and _dev database required")
    return psycopg.connect(
        host="127.0.0.1",
        port=55432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=psycopg.rows.dict_row,
    )


def load_movement(movement_id):
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


def canonical_created_at(value):
    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )
    else:
        value = value.astimezone(
            timezone.utc
        )

    return value.isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def canonical_json(row):
    payload = {
        "created_at": canonical_created_at(
            row["created_at"]
        ),
        "id": row["id"],
        "inventory_item_id": row[
            "inventory_item_id"
        ],
        "movement_type": row[
            "movement_type"
        ],
        "notes": row["notes"],
        "quantity_after": row[
            "quantity_after"
        ],
        "quantity_before": row[
            "quantity_before"
        ],
        "quantity_change": row[
            "quantity_change"
        ],
        "reference_id": row[
            "reference_id"
        ],
        "reference_type": row[
            "reference_type"
        ],
        "source_system": row[
            "source_system"
        ],
        "warehouse_id": row[
            "warehouse_id"
        ],
    }

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def load_keypair():
    raw = json.loads(
        KEYPAIR_PATH.read_text()
    )

    return Keypair.from_bytes(
        bytes(raw)
    )


def save_signature(
    movement_id,
    signature,
):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_movements
                SET blockchain_signature = %s
                WHERE id = %s
                  AND blockchain_signature IS NULL
                """,
                (
                    signature,
                    movement_id,
                ),
            )

            if cur.rowcount != 1:
                cur.execute(
                    """
                    SELECT blockchain_signature
                    FROM inventory_movements
                    WHERE id = %s
                    """,
                    (movement_id,),
                )

                row = cur.fetchone()

                if row is None:
                    raise RuntimeError(
                        f"Movement {movement_id} "
                        "disappeared during signature save."
                    )

                existing = row[
                    "blockchain_signature"
                ]

                if existing == signature:
                    return

                raise RuntimeError(
                    f"Movement {movement_id} signature "
                    "was not updated. Existing value: "
                    f"{existing!r}"
                )

        conn.commit()


def load_existing_audit(audit_pda):
    result = rpc(
        "getAccountInfo",
        [
            str(audit_pda),
            {
                "encoding": "base64",
                "commitment": "confirmed",
            },
        ],
    )

    account = result["value"]

    if account is None:
        return None

    if account["owner"] != str(PROGRAM_ID):
        raise RuntimeError(
            "Audit PDA exists but is owned by "
            f'{account["owner"]}, not {PROGRAM_ID}.'
        )

    raw = base64.b64decode(
        account["data"][0]
    )

    if len(raw) != 120:
        raise RuntimeError(
            "Audit PDA has unexpected data length: "
            f"{len(raw)}"
        )

    if raw[:8] != INVENTORY_AUDIT_DISCRIMINATOR:
        raise RuntimeError(
            "Audit PDA has an unexpected "
            "account discriminator."
        )

    offset = 8

    authority = Pubkey.from_bytes(
        raw[offset:offset + 32]
    )
    offset += 32

    movement_id = struct.unpack_from(
        "<Q",
        raw,
        offset,
    )[0]
    offset += 8

    inventory_item_id = struct.unpack_from(
        "<Q",
        raw,
        offset,
    )[0]
    offset += 8

    quantity_change = struct.unpack_from(
        "<q",
        raw,
        offset,
    )[0]
    offset += 8

    quantity_before = struct.unpack_from(
        "<q",
        raw,
        offset,
    )[0]
    offset += 8

    quantity_after = struct.unpack_from(
        "<q",
        raw,
        offset,
    )[0]
    offset += 8

    audit_hash = raw[offset:offset + 32]
    offset += 32

    recorded_at = struct.unpack_from(
        "<q",
        raw,
        offset,
    )[0]

    return {
        "authority": authority,
        "movement_id": movement_id,
        "inventory_item_id": inventory_item_id,
        "quantity_change": quantity_change,
        "quantity_before": quantity_before,
        "quantity_after": quantity_after,
        "audit_hash": audit_hash,
        "recorded_at": recorded_at,
    }


def verify_existing_audit(
    existing,
    movement,
    digest,
    signer,
):
    expected = {
        "authority": signer.pubkey(),
        "movement_id": movement["id"],
        "inventory_item_id": movement[
            "inventory_item_id"
        ],
        "quantity_change": movement[
            "quantity_change"
        ],
        "quantity_before": movement[
            "quantity_before"
        ],
        "quantity_after": movement[
            "quantity_after"
        ],
        "audit_hash": digest,
    }

    for field, expected_value in expected.items():
        actual_value = existing[field]

        if actual_value != expected_value:
            raise RuntimeError(
                "BLOCKCHAIN INTEGRITY ERROR: "
                f"existing PDA field {field} "
                f"does not match PostgreSQL. "
                f"Expected {expected_value!r}, "
                f"found {actual_value!r}."
            )


def recover_pda_signature(audit_pda):
    signatures = rpc(
        "getSignaturesForAddress",
        [
            str(audit_pda),
            {
                "limit": 10,
                "commitment": "confirmed",
            },
        ],
    )

    for entry in signatures:
        if entry.get("err") is None:
            return entry["signature"]

    return f"pda:{audit_pda}"


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python send_movement.py MOVEMENT_ID"
        )

    movement_id = int(sys.argv[1])
    movement = load_movement(
        movement_id
    )

    if movement[
        "blockchain_signature"
    ]:
        raise SystemExit(
            f"Movement {movement_id} already has "
            "a blockchain signature."
        )

    canonical = canonical_json(
        movement
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8")
    ).digest()

    movement_seed = movement_id.to_bytes(
        8,
        byteorder="little",
        signed=False,
    )

    audit_pda, bump = (
        Pubkey.find_program_address(
            [
                b"inventory-audit",
                movement_seed,
            ],
            PROGRAM_ID,
        )
    )

    signer = load_keypair()

    existing = load_existing_audit(
        audit_pda
    )

    if existing is not None:
        print(
            "===== EXISTING BLOCKCHAIN AUDIT ====="
        )
        print(
            "Movement:",
            movement_id,
        )
        print(
            "PDA:",
            audit_pda,
        )

        verify_existing_audit(
            existing,
            movement,
            digest,
            signer,
        )

        print(
            "Existing PDA matches PostgreSQL."
        )

        recovered_signature = (
            recover_pda_signature(
                audit_pda
            )
        )

        print(
            "Recovered transaction signature:",
            recovered_signature,
        )

        save_signature(
            movement_id,
            recovered_signature,
        )

        print(
            "Database signature: RECOVERED"
        )
        return

    data = (
        ANCHOR_DISCRIMINATOR
        + struct.pack(
            "<Q",
            movement["id"],
        )
        + struct.pack(
            "<Q",
            movement[
                "inventory_item_id"
            ],
        )
        + struct.pack(
            "<q",
            movement[
                "quantity_change"
            ],
        )
        + struct.pack(
            "<q",
            movement[
                "quantity_before"
            ],
        )
        + struct.pack(
            "<q",
            movement[
                "quantity_after"
            ],
        )
        + digest
    )

    instruction = Instruction(
        PROGRAM_ID,
        data,
        [
            AccountMeta(
                signer.pubkey(),
                True,
                True,
            ),
            AccountMeta(
                audit_pda,
                False,
                True,
            ),
            AccountMeta(
                SYSTEM_PROGRAM,
                False,
                False,
            ),
        ],
    )

    latest = rpc(
        "getLatestBlockhash",
        [
            {
                "commitment":
                "confirmed"
            }
        ],
    )

    blockhash = Hash.from_string(
        latest["value"][
            "blockhash"
        ]
    )

    transaction = (
        Transaction.new_signed_with_payer(
            [instruction],
            signer.pubkey(),
            [signer],
            blockhash,
        )
    )

    encoded = base64.b64encode(
        bytes(transaction)
    ).decode()

    print(
        "===== BLOCKCHAIN AUDIT SEND ====="
    )
    print(
        "Movement:",
        movement_id,
    )
    print(
        "Signer:",
        signer.pubkey(),
    )
    print(
        "PDA:",
        audit_pda,
    )
    print(
        "Bump:",
        bump,
    )
    print(
        "Hash:",
        digest.hex(),
    )

    signature = rpc(
        "sendTransaction",
        [
            encoded,
            {
                "encoding": "base64",
                "preflightCommitment":
                "confirmed",
            },
        ],
    )

    print(
        "Transaction signature:",
        signature,
    )

    for attempt in range(30):
        statuses = rpc(
            "getSignatureStatuses",
            [
                [signature],
                {
                    "searchTransactionHistory":
                    True
                },
            ],
        )

        status = statuses[
            "value"
        ][0]

        if status:
            if status["err"] is not None:
                raise RuntimeError(
                    f"Transaction failed: "
                    f'{status["err"]}'
                )

            confirmation = status.get(
                "confirmationStatus"
            )

            if confirmation in {
                "confirmed",
                "finalized",
            }:
                print(
                    "Confirmation:",
                    confirmation,
                )

                save_signature(
                    movement_id,
                    signature,
                )

                print(
                    "Database signature: UPDATED"
                )
                return

        time.sleep(1)

    raise RuntimeError(
        "Transaction was sent but confirmation "
        "timed out. Database was not updated."
    )


if __name__ == "__main__":
    main()
