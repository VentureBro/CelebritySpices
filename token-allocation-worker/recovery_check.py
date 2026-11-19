import json

from preflight import database_connection
from execute import rpc_call


def main():
    print("===== TOKEN TRANSFER RECOVERY INSPECTION =====")

    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.id AS allocation_id,
                    a.status AS allocation_status,
                    j.status AS journal_status,
                    j.transaction_signature,
                    j.destination_token_account,
                    j.amount_base_units
                FROM token_allocations a
                LEFT JOIN token_transfer_attempts j
                    ON j.allocation_id = a.id
                WHERE a.status = 'processing'
                   OR j.status IN (
                       'reserved',
                       'broadcasting',
                       'submitted',
                       'requires_reconciliation'
                   )
                ORDER BY a.id
                """
            )
            rows = cur.fetchall()

    print("Unresolved allocations:", len(rows))

    for row in rows:
        print()
        print("Allocation:", row["allocation_id"])
        print("Allocation status:", row["allocation_status"])
        print("Journal status:", row["journal_status"])

        signature = row["transaction_signature"]

        if not signature:
            print("Signature: NOT RECORDED")
            print("ACTION: Manual reconciliation required")
            print("DO NOT RETRY")
            continue

        print("Signature:", signature)

        try:
            result = rpc_call(
                "getSignatureStatuses",
                [
                    [signature],
                    {"searchTransactionHistory": True},
                ],
            )

            status = result["value"][0]

            if status is None:
                print("On-chain status: NOT FOUND")
                print("ACTION: Manual reconciliation required")
            else:
                print("On-chain status:")
                print(json.dumps(status, indent=2))
                print("ACTION: Review before any database update")

        except Exception as exc:
            print("RPC inspection failed:", str(exc))
            print("ACTION: Manual reconciliation required")

        print("DO NOT RETRY")

    print()
    print("INSPECTION COMPLETE — NO TRANSACTIONS EXECUTED")


if __name__ == "__main__":
    main()
