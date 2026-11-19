"""Safety-locked atomic confirmation executor."""
from preflight import database_connection
from trusted_finalized_coordinator import verify_journaled_finalization
from trusted_atomic_reconciliation import validate_locked_reconciliation

def execute_trusted_confirmation(allocation_id):
    raise RuntimeError("SAFETY LOCK: atomic confirmation execution disabled")

def _confirm_inside_transaction(conn, allocation_id, signed, signature):
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
        record = cur.fetchone()
        validate_locked_reconciliation(record, signed, signature)
        raise RuntimeError("SAFETY LOCK: database confirmation updates disabled")
        from trusted_confirmation_sql import CONFIRM_JOURNAL_SQL, CONFIRM_ALLOCATION_SQL
        cur.execute(CONFIRM_JOURNAL_SQL, (allocation_id, signature, signed, record["destination_token_account"], record["allocation_amount"]))
        if cur.fetchone() is None:
            raise RuntimeError("Journal confirmation rejected")
        cur.execute(CONFIRM_ALLOCATION_SQL, (signature, allocation_id, record["allocation_amount"], record["token_decimals"]))
        if cur.fetchone() is None:
            raise RuntimeError("Allocation confirmation rejected")
    return signature

def _prepare_trusted_confirmation(allocation_id):
    from trusted_evidence_binding import verify_bound_evidence
    signed, signature = verify_bound_evidence(allocation_id)
    if not isinstance(signed, bytes) or not signed:
        raise ValueError("Verified transaction bytes required")
    if not isinstance(signature, str) or not signature:
        raise ValueError("Verified transaction signature required")
    raise RuntimeError("SAFETY LOCK: verified evidence prepared; database confirmation disabled")

def _verify_and_check_locked(allocation_id):
    from trusted_evidence_binding import verify_bound_evidence
    signed, signature = verify_bound_evidence(allocation_id)
    if not isinstance(signed, bytes) or not signed:
        raise ValueError("Verified transaction bytes required")
    if not isinstance(signature, str) or not signature:
        raise ValueError("Verified transaction signature required")
    with database_connection() as conn:
        try:
            _confirm_inside_transaction(conn, allocation_id, signed, signature)
            raise RuntimeError("SAFETY LOCK: confirmation must remain disabled")
        finally:
            conn.rollback()
