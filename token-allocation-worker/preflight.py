import os
import sys

import psycopg
from psycopg.rows import dict_row


TOKEN_MINT = "55wALPPSEqNcpMRRQ33oMj7pBErH7eLgN2FTdgUtXuuE"
TREASURY_WALLET = "G1TpwMhcQJ5Kt2P594dimcJ6i1P11FuzCJwZkVEu5oUW"
TREASURY_TOKEN_ACCOUNT = "45ybNYUvzwMkPQ3qrSN3ALX2QsEkt6T2TxHU1Jw4crUN"
TOKEN_DECIMALS = 2


def database_connection():
    if os.environ.get("CELEBRITYSPICES_DEV_DB_ALLOWED") != "1" or not os.environ.get("POSTGRES_DB", "").endswith("_dev"):
        raise RuntimeError("Development database connection blocked: explicit authorization and _dev database required")
    return psycopg.connect(
        host="127.0.0.1",
        port=55432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=dict_row,
    )


def load_allocation(allocation_id: int):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.id,
                    a.wallet_id,
                    a.amount_base_units,
                    a.token_decimals,
                    a.allocation_type,
                    a.blockchain_signature,
                    a.status,
                    a.notes,
                    w.wallet_address,
                    w.token_account_address,
                    w.status AS wallet_status
                FROM token_allocations a
                JOIN token_wallets w
                  ON w.id = a.wallet_id
                WHERE a.id = %s
                """,
                (allocation_id,),
            )
            return cur.fetchone()


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: preflight.py <allocation_id>"
        )

    allocation_id = int(sys.argv[1])
    row = load_allocation(allocation_id)

    if row is None:
        raise SystemExit("Allocation not found")

    if row["status"] != "approved":
        raise SystemExit(
            f"Allocation status is '{row['status']}', not 'approved'"
        )

    if row["blockchain_signature"] is not None:
        raise SystemExit(
            "Allocation already has a blockchain signature"
        )

    if row["wallet_status"] != "active":
        raise SystemExit("Destination wallet is not active")

    if not row["token_account_address"]:
        raise SystemExit(
            "Destination token account is missing"
        )

    if row["token_decimals"] != TOKEN_DECIMALS:
        raise SystemExit(
            "Allocation token decimals do not match configured token"
        )

    amount_base_units = row["amount_base_units"]

    if amount_base_units <= 0:
        raise SystemExit(
            "Allocation amount must be greater than zero"
        )

    scale = 10 ** TOKEN_DECIMALS

    whole = amount_base_units // scale
    fraction = amount_base_units % scale

    amount_tokens = (
        f"{whole}.{fraction:0{TOKEN_DECIMALS}d}"
    )

    print("===== TOKEN ALLOCATION PREFLIGHT =====")
    print("Allocation:", row["id"])
    print("Status:", row["status"])
    print("Type:", row["allocation_type"])
    print()
    print("Mint:", TOKEN_MINT)
    print("Treasury wallet:", TREASURY_WALLET)
    print(
        "Treasury token account:",
        TREASURY_TOKEN_ACCOUNT,
    )
    print()
    print(
        "Destination wallet:",
        row["wallet_address"],
    )
    print(
        "Destination token account:",
        row["token_account_address"],
    )
    print()
    print(
        "Amount base units:",
        amount_base_units,
    )
    print(
        "Amount tokens:",
        amount_tokens,
    )
    print()
    print("PREFLIGHT RESULT: APPROVED FOR CHAIN CHECK")
    print("NO TRANSACTION HAS BEEN SIGNED OR SENT")


if __name__ == "__main__":
    main()


# Live-chain validation is implemented separately from main()
# for the next execution stage.
