"""Parameterized SQL for trusted atomic confirmation."""

CONFIRM_JOURNAL_SQL = """
UPDATE token_transfer_attempts
SET status = 'confirmed', confirmed_at = NOW(), updated_at = NOW()
WHERE allocation_id = %s
  AND status IN ('broadcasting', 'submitted', 'requires_reconciliation')
  AND transaction_signature = %s
  AND signed_transaction = %s
  AND destination_token_account = %s
  AND amount_base_units = %s
RETURNING id
"""

CONFIRM_ALLOCATION_SQL = """
UPDATE token_allocations
SET status = 'confirmed', blockchain_signature = %s, confirmed_at = NOW()
WHERE id = %s
  AND status = 'processing'
  AND blockchain_signature IS NULL
  AND amount_base_units = %s
  AND token_decimals = %s
RETURNING id
"""
