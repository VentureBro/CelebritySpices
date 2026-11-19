from signed_recovery_inspector import (
    inspect_unresolved_transactions,
    classify_transaction,
)
from solana_recovery_rpc import inspect_signed_transaction


def inspect_all():
    records = inspect_unresolved_transactions()

    print("===== INTEGRATED SOLANA RECOVERY INSPECTION =====")
    print(f"Unresolved transactions: {len(records)}")

    for record in records:
        allocation_id = record["allocation_id"]
        signature = record["transaction_signature"]
        last_valid = record["last_valid_block_height"]

        classification = classify_transaction(record)

        print()
        print("Allocation:", allocation_id)
        print("Journal status:", record["status"])
        print("Allocation status:", record["allocation_status"])
        print("Journal classification:", classification)

        if classification != "SIGNED_TRANSACTION_REQUIRES_CHAIN_CHECK":
            print("Action: MANUAL_REVIEW_REQUIRED")
            continue

        if not isinstance(last_valid, int) or last_valid <= 0:
            print("Action: INVALID_BLOCK_HEIGHT_MANUAL_REVIEW")
            continue

        try:
            result = inspect_signed_transaction(
                signature,
                last_valid,
            )

            print("Chain classification:", result["classification"])
            print("Current block height:", result["current_block_height"])
            print("Last valid block height:", last_valid)
            print(
                "Validity height exceeded:",
                result["blockhash_height_exceeded"],
            )

            if result["requires_reconciliation"]:
                print("Action: RECONCILIATION_REQUIRED")
            else:
                print("Action: FINALIZED_REQUIRES_DB_VERIFICATION")

        except Exception as exc:
            print("RPC inspection failed:", type(exc).__name__)
            print("Action: MANUAL_REVIEW_REQUIRED")

    print()
    print("INSPECTION COMPLETE")
    print("NO DATABASE MODIFICATIONS")
    print("NO TRANSACTIONS BROADCAST")


if __name__ == "__main__":
    inspect_all()
