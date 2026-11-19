from preflight import database_connection


def confirm_verified_allocation(allocation_id, signature, verification):
    raise RuntimeError("SAFETY LOCK: legacy allocation confirmation disabled; trusted atomic reconciliation required")
    if not isinstance(verification, dict):
        raise ValueError("Verification evidence required")

    if verification.get("classification") != "FINALIZED_SUCCESS":
        raise ValueError("Transaction is not finalized")

    if verification.get("signature") != signature:
        raise ValueError("Verification signature mismatch")

    if verification.get("transfer_verified") is not True:
        raise ValueError("Transfer details not verified")

    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE token_transfer_attempts
                SET status = 'confirmed',
                    confirmed_at = NOW(),
                    updated_at = NOW()
                WHERE allocation_id = %s
                  AND status IN (
                      'broadcasting',
                      'submitted',
                      'requires_reconciliation'
                  )
                  AND transaction_signature = %s
                  AND signed_transaction IS NOT NULL
                  AND recent_blockhash IS NOT NULL
                  AND last_valid_block_height IS NOT NULL
                RETURNING id
                """,
                (allocation_id, signature),
            )

            if cur.fetchone() is None:
                raise RuntimeError("Journal confirmation rejected")

            cur.execute(
                """
                UPDATE token_allocations
                SET status = 'confirmed',
                    blockchain_signature = %s,
                    confirmed_at = NOW()
                WHERE id = %s
                  AND status = 'processing'
                  AND blockchain_signature IS NULL
                RETURNING id
                """,
                (signature, allocation_id),
            )

            if cur.fetchone() is None:
                raise RuntimeError("Allocation confirmation rejected")

        conn.commit()

    return signature
