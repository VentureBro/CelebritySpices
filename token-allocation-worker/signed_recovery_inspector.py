from preflight import database_connection


UNRESOLVED_STATUSES = (
    "reserved",
    "broadcasting",
    "submitted",
    "requires_reconciliation",
)


def inspect_unresolved_transactions():
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    t.allocation_id,
                    t.status,
                    t.transaction_signature,
                    t.signed_transaction IS NOT NULL
                        AS has_signed_transaction,
                    t.recent_blockhash,
                    t.last_valid_block_height,
                    a.status AS allocation_status
                FROM token_transfer_attempts t
                JOIN token_allocations a
                  ON a.id = t.allocation_id
                WHERE t.status = ANY(%s)
                ORDER BY t.allocation_id
                """,
                (list(UNRESOLVED_STATUSES),),
            )

            return cur.fetchall()


def classify_transaction(record):
    status = record["status"]
    signature = record["transaction_signature"]
    has_signed = record["has_signed_transaction"]

    if signature and has_signed:
        return "SIGNED_TRANSACTION_REQUIRES_CHAIN_CHECK"

    if signature and not has_signed:
        return "SIGNATURE_EXISTS_WITHOUT_SIGNED_BYTES"

    if has_signed and not signature:
        return "SIGNED_BYTES_EXIST_WITHOUT_SIGNATURE"

    if status == "reserved":
        return "UNSIGNED_RESERVATION_REQUIRES_REVIEW"

    return "INCOMPLETE_TRANSACTION_REQUIRES_REVIEW"


def main():
    records = inspect_unresolved_transactions()

    print("===== SIGNED TRANSACTION RECOVERY =====")
    print(f"Unresolved transactions: {len(records)}")

    for record in records:
        classification = classify_transaction(record)

        print()
        print(f"Allocation: {record['allocation_id']}")
        print(f"Journal status: {record['status']}")
        print(f"Allocation status: {record['allocation_status']}")
        print(f"Recovery classification: {classification}")

        if record["transaction_signature"]:
            print(
                "Transaction signature:",
                record["transaction_signature"],
            )

    print()
    print("INSPECTION COMPLETE")
    print("NO TRANSACTIONS BROADCAST")


if __name__ == "__main__":
    main()
