"""Read-only loader for journal-backed reconciliation."""
from preflight import database_connection

def load_reconciliation_record(allocation_id):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT a.id AS allocation_id, a.status AS allocation_status,
                       a.blockchain_signature, a.amount_base_units AS allocation_amount,
                       a.token_decimals, w.token_account_address,
                       w.status AS wallet_status, t.status AS journal_status,
                       t.destination_token_account, t.amount_base_units AS journal_amount,
                       t.transaction_signature, t.signed_transaction,
                       t.recent_blockhash, t.last_valid_block_height
                FROM token_transfer_attempts t
                JOIN token_allocations a ON a.id = t.allocation_id
                JOIN token_wallets w ON w.id = a.wallet_id
                WHERE t.allocation_id = %s""",
                (allocation_id,),
            )
            record = cur.fetchone()
        conn.rollback()
    return record
