"""Trusted reconciliation foundation; confirmation remains disabled."""
from preflight import database_connection

def load_locked_reconciliation_record(allocation_id):
    with database_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.id AS allocation_id, a.status AS allocation_status,
                              a.blockchain_signature, a.amount_base_units AS allocation_amount,
                              a.token_decimals, w.token_account_address,
                              w.status AS wallet_status, t.status AS journal_status,
                              t.destination_token_account, t.amount_base_units AS journal_amount,
                              t.transaction_signature, t.signed_transaction,
                              t.recent_blockhash, t.last_valid_block_height
                       FROM token_allocations a
                       JOIN token_wallets w ON w.id = a.wallet_id
                       JOIN token_transfer_attempts t ON t.allocation_id = a.id
                       WHERE a.id = %s
                       FOR UPDATE OF a, w, t""",
                    (allocation_id,),
                )
                return cur.fetchone()
        finally:
            conn.rollback()

def confirm_trusted_allocation(allocation_id):
    raise RuntimeError("SAFETY LOCK: trusted atomic confirmation not implemented")

def validate_locked_reconciliation(record, expected_signed, expected_signature):
    from trusted_reconciliation_validator import validate_reconciliation_record
    if not isinstance(expected_signed, bytes) or not expected_signed:
        raise ValueError("Expected signed transaction required")
    if not isinstance(expected_signature, str) or not expected_signature:
        raise ValueError("Expected signature required")
    signed, signature = validate_reconciliation_record(record)
    if signed != expected_signed:
        raise ValueError("Signed transaction changed after verification")
    if signature != expected_signature:
        raise ValueError("Transaction signature changed after verification")
    return True
