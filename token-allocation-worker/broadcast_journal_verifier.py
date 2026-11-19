"""Verify a committed signed transaction before broadcasting."""

from preflight import database_connection


def verify_broadcast_ready(allocation_id, prepared):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, transaction_signature, signed_transaction,
                       recent_blockhash, last_valid_block_height
                FROM token_transfer_attempts
                WHERE allocation_id = %s
                """,
                (allocation_id,),
            )
            record = cur.fetchone()

    if record is None:
        raise RuntimeError("Journal record missing")

    if record["status"] != "broadcasting":
        raise RuntimeError("Journal not in broadcasting state")

    if record["transaction_signature"] != prepared["signature"]:
        raise RuntimeError("Journal signature mismatch")

    if record["signed_transaction"] is None:
        raise RuntimeError("Signed transaction missing")

    if bytes(record["signed_transaction"]) != prepared["signed_transaction"]:
        raise RuntimeError("Signed transaction bytes mismatch")

    if record["recent_blockhash"] != prepared["recent_blockhash"]:
        raise RuntimeError("Blockhash mismatch")

    if record["last_valid_block_height"] != prepared["last_valid_block_height"]:
        raise RuntimeError("Block height mismatch")

    return True
