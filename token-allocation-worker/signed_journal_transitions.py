from preflight import database_connection


def mark_signed_broadcasting(allocation_id, signature):
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
                  AND transaction_signature = %s
                  AND signed_transaction IS NOT NULL
                  AND recent_blockhash IS NOT NULL
                  AND last_valid_block_height IS NOT NULL
                """,
                (allocation_id, signature),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Cannot transition signed journal to broadcasting"
                )

        conn.commit()


def mark_signed_submitted(allocation_id, signature):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE token_transfer_attempts
                SET
                    status = 'submitted',
                    updated_at = NOW()
                WHERE allocation_id = %s
                  AND status = 'broadcasting'
                  AND transaction_signature = %s
                  AND signed_transaction IS NOT NULL
                """,
                (allocation_id, signature),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Cannot transition signed journal to submitted"
                )

        conn.commit()
