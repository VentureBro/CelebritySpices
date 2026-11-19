"""Bind finalized Solana evidence to journaled transaction bytes."""
from trusted_finalized_coordinator import load_reconciliation_record, validate_reconciliation_record, verify_finalized_transfer
from preflight import TOKEN_MINT, TOKEN_DECIMALS, TREASURY_WALLET, TREASURY_TOKEN_ACCOUNT

def verify_bound_evidence(allocation_id):
    record = load_reconciliation_record(allocation_id)
    signed, signature = validate_reconciliation_record(record)
    result = verify_finalized_transfer(
        signed, signature, TREASURY_WALLET, TREASURY_TOKEN_ACCOUNT,
        record["destination_token_account"], TOKEN_MINT,
        record["allocation_amount"], TOKEN_DECIMALS,
    )
    if not isinstance(result, dict):
        raise ValueError("Invalid finalized verification result")
    if result.get("classification") != "FINALIZED_SUCCESS":
        raise ValueError("Transaction not finalized")
    if result.get("signature") != signature:
        raise ValueError("Finalized signature mismatch")
    if result.get("transfer_verified") is not True:
        raise ValueError("Transfer verification failed")
    return signed, signature
