import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

from preflight import (
    TOKEN_DECIMALS,
    TOKEN_MINT,
    TREASURY_TOKEN_ACCOUNT,
    load_allocation,
    database_connection,
)

RPC_URL = "http://127.0.0.1:8899"

TREASURY_KEY = (
    "/home/pi/Projects/Solana/private-token/"
    "keys/treasury.json"
)

SPL_TOKEN = (
    "/home/pi/Projects/Solana/agave/bin/spl-token"
)

WORKER_PYTHON = (
    "/home/pi/OperationsPlatform/"
    "blockchain-worker/.venv/bin/python"
)

CHAIN_CHECK = (
    "/home/pi/OperationsPlatform/"
    "token-allocation-worker/chain_check.py"
)


def token_amount(base_units, decimals):
    scale = 10 ** decimals
    whole = base_units // scale
    fraction = base_units % scale

    return (
        f"{whole}."
        f"{fraction:0{decimals}d}"
    )


def run_chain_check(allocation_id):
    result = subprocess.run(
        [
            WORKER_PYTHON,
            CHAIN_CHECK,
            str(allocation_id),
        ],
        text=True,
        capture_output=True,
    )

    print(result.stdout, end="")

    if result.returncode != 0:
        if result.stderr:
            print(
                result.stderr,
                file=sys.stderr,
            )

        raise SystemExit(
            "LIVE CHAIN PREFLIGHT FAILED"
        )



def rpc_call(method, params):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")

    request = urllib.request.Request(
        RPC_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=5,
    ) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    if "error" in result:
        raise RuntimeError(
            f"RPC error: {result['error']}"
        )

    return result["result"]


def verify_signature(signature):
    for attempt in range(15):
        result = rpc_call(
            "getSignatureStatuses",
            [
                [signature],
                {
                    "searchTransactionHistory": True,
                },
            ],
        )

        status = result["value"][0]

        if status is not None:
            if status["err"] is not None:
                raise RuntimeError(
                    f"Transaction failed: {status['err']}"
                )

            confirmation = status.get(
                "confirmationStatus"
            )

            if confirmation in (
                "confirmed",
                "finalized",
            ):
                return status

        time.sleep(1)

    raise RuntimeError(
        "Transaction was broadcast but confirmation "
        "was not observed within 15 seconds"
    )


def reserve_allocation(allocation_id, destination, amount_base):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE token_allocations
                SET status = 'processing'
                WHERE id = %s
                  AND status = 'approved'
                  AND blockchain_signature IS NULL
                RETURNING id
                """,
                (allocation_id,),
            )

            if cur.fetchone() is None:
                raise RuntimeError(
                    "Allocation already claimed or not approved"
                )

            cur.execute(
                """
                INSERT INTO token_transfer_attempts (
                    allocation_id,
                    destination_token_account,
                    amount_base_units,
                    status
                )
                VALUES (%s, %s, %s, 'reserved')
                """,
                (allocation_id, destination, amount_base),
            )

        conn.commit()

def mark_confirmed(allocation_id, signature):
    confirmed_at = datetime.now(timezone.utc)

    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE token_transfer_attempts
                SET
                    transaction_signature = %s,
                    status = 'confirmed',
                    confirmed_at = %s,
                    updated_at = %s
                WHERE allocation_id = %s
                  AND status IN (
                      'reserved',
                      'broadcasting',
                      'submitted',
                      'requires_reconciliation'
                  )
                  AND (
                      transaction_signature IS NULL
                      OR transaction_signature = %s
                  )
                """,
                (
                    signature,
                    confirmed_at,
                    confirmed_at,
                    allocation_id,
                    signature,
                ),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Journal confirmation update failed"
                )

            cur.execute(
                """
                UPDATE token_allocations
                SET
                    blockchain_signature = %s,
                    status = 'confirmed',
                    confirmed_at = %s
                WHERE id = %s
                  AND status = 'processing'
                  AND blockchain_signature IS NULL
                """,
                (
                    signature,
                    confirmed_at,
                    allocation_id,
                ),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Allocation confirmation update failed"
                )

        conn.commit()


def mark_broadcasting(allocation_id):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE token_transfer_attempts
                SET
                    status = 'broadcasting',
                    updated_at = NOW()
                WHERE allocation_id = %s
                  AND status = 'reserved'
                  AND transaction_signature IS NULL
                """,
                (allocation_id,),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Cannot transition journal to broadcasting"
                )

        conn.commit()



def mark_requires_reconciliation(allocation_id, reason):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE token_transfer_attempts
                SET
                    status = 'requires_reconciliation',
                    error_message = %s,
                    updated_at = NOW()
                WHERE allocation_id = %s
                  AND status IN (
                      'reserved',
                      'broadcasting',
                      'submitted'
                  )
                """,
                (reason, allocation_id),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Could not mark transfer for reconciliation"
                )

        conn.commit()



def mark_submitted(allocation_id, signature):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE token_transfer_attempts
                SET
                    transaction_signature = %s,
                    status = 'submitted',
                    updated_at = NOW()
                WHERE allocation_id = %s
                  AND status = 'broadcasting'
                  AND transaction_signature IS NULL
                """,
                (signature, allocation_id),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Could not record submitted transaction"
                )

        conn.commit()


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(
            "Usage: execute.py "
            "<allocation_id> [--execute]"
        )

    allocation_id = int(sys.argv[1])

    execute = (
        len(sys.argv) == 3
        and sys.argv[2] == "--execute"
    )

    if len(sys.argv) == 3 and not execute:
        raise SystemExit(
            "Only --execute is accepted"
        )

    row = load_allocation(allocation_id)

    if row is None:
        raise SystemExit(
            "Allocation not found"
        )

    if row["status"] != "approved":
        raise SystemExit(
            f"Refusing: allocation status is "
            f"'{row['status']}'"
        )

    if row["blockchain_signature"] is not None:
        raise SystemExit(
            "Refusing: allocation already has "
            "a blockchain signature"
        )

    if row["wallet_status"] != "active":
        raise SystemExit(
            "Refusing: wallet is not active"
        )

    if not row["token_account_address"]:
        raise SystemExit(
            "Refusing: destination missing"
        )

    if row["token_decimals"] != TOKEN_DECIMALS:
        raise SystemExit(
            "Refusing: decimals mismatch"
        )

    amount_base = int(
        row["amount_base_units"]
    )

    if amount_base <= 0:
        raise SystemExit(
            "Refusing: invalid amount"
        )

    amount = token_amount(
        amount_base,
        TOKEN_DECIMALS,
    )

    print(
        "===== FINAL LIVE CHAIN CHECK ====="
    )

    run_chain_check(allocation_id)

    print()
    print(
        "===== TOKEN EXECUTION PLAN ====="
    )
    print("Allocation:", allocation_id)
    print("Wallet:", row["wallet_address"])
    print(
        "Destination:",
        row["token_account_address"],
    )
    print("Amount:", amount)
    print("Mint:", TOKEN_MINT)

    if not execute:
        print()
        print(
            "EXECUTION STATUS: PREPARED ONLY"
        )
        print(
            "Run with --execute to broadcast."
        )
        return

    raise SystemExit(
        "SAFETY LOCK: Legacy spl-token transfer execution "
        "is disabled until signed transaction journaling "
        "and recovery are integrated."
    )

    reserve_allocation(
        allocation_id,
        row["token_account_address"],
        amount_base,
    )

    print("ALLOCATION RESERVED: processing")

    print()
    mark_broadcasting(allocation_id)

    print(
        "===== BROADCASTING TRANSFER ====="
    )

    command = [
        SPL_TOKEN,
        "transfer",
        "--url",
        RPC_URL,
        "--owner",
        TREASURY_KEY,
        "--from",
        TREASURY_TOKEN_ACCOUNT,
        "--output",
        "json",
        TOKEN_MINT,
        amount,
        row["token_account_address"],
    ]

    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        mark_requires_reconciliation(
            allocation_id,
            "Solana CLI timed out; transaction outcome unknown",
        )
        raise SystemExit(
            "TRANSFER TIMED OUT — journal marked for reconciliation. "
            "DO NOT RETRY until on-chain activity is verified."
        )

    if result.returncode != 0:
        mark_requires_reconciliation(
            allocation_id,
            "Solana CLI returned a nonzero exit code; "
            "transaction outcome requires verification",
        )

        print(
            result.stderr,
            file=sys.stderr,
        )

        raise SystemExit(
            "SOLANA CLI ERROR — transaction outcome unknown. "
            "Journal marked for reconciliation. "
            "DO NOT RETRY automatically."
        )

    try:
        transfer = json.loads(
            result.stdout
        )
    except json.JSONDecodeError:
        mark_requires_reconciliation(
            allocation_id,
            "Solana CLI returned invalid JSON; "
            "transaction outcome unknown",
        )
        print(result.stdout)
        raise SystemExit(
            "INVALID TRANSFER RESPONSE — "
            "journal marked for reconciliation. "
            "DO NOT RETRY automatically."
        )

    signature = (
        transfer.get("signature")
        or transfer.get("transactionSignature")
    )

    if not signature:
        mark_requires_reconciliation(
            allocation_id,
            "Solana CLI response contained no signature; "
            "transaction outcome unknown",
        )
        print(
            json.dumps(
                transfer,
                indent=2,
            )
        )
        raise SystemExit(
            "NO TRANSACTION SIGNATURE — "
            "journal marked for reconciliation. "
            "DO NOT RETRY automatically."
        )

    print(
        "Transaction signature:",
        signature,
    )

    print()
    print(
        "===== VERIFYING ON-CHAIN ====="
    )

    mark_submitted(allocation_id, signature)

    try:
        status = verify_signature(signature)
    except Exception as exc:
        mark_requires_reconciliation(
            allocation_id,
            "Confirmation check failed: " + str(exc)[:500],
        )
        raise SystemExit(
            "CONFIRMATION UNKNOWN — journal requires reconciliation. "
            "DO NOT RETRY automatically."
        ) from exc

    print(
        "Confirmation status:",
        status.get("confirmationStatus"),
    )
    print(
        "Transaction error:",
        status.get("err"),
    )

    mark_confirmed(
        allocation_id,
        signature,
    )

    print()
    print(
        "DATABASE STATUS: CONFIRMED"
    )
    print(
        "Allocation:",
        allocation_id,
    )
    print(
        "Confirmed at:",
        datetime.now(
            timezone.utc
        ).isoformat(),
    )


if __name__ == "__main__":
    main()
