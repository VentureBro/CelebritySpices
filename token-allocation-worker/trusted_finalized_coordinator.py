"""Read-only journal-backed finalized transaction verification."""
from preflight import TOKEN_MINT, TOKEN_DECIMALS, TREASURY_WALLET, TREASURY_TOKEN_ACCOUNT
from trusted_reconciliation_loader import load_reconciliation_record
from trusted_reconciliation_validator import validate_reconciliation_record
from finalized_transaction_verifier import verify_finalized_transfer

def verify_journaled_finalization(allocation_id):
    record = load_reconciliation_record(allocation_id)
    signed, signature = validate_reconciliation_record(record)
    result = verify_finalized_transfer(
        signed,
        signature,
        TREASURY_WALLET,
        TREASURY_TOKEN_ACCOUNT,
        record["destination_token_account"],
        TOKEN_MINT,
        record["allocation_amount"],
        TOKEN_DECIMALS,
    )
    if result.get("classification") != "FINALIZED_SUCCESS":
        raise ValueError("Transaction not finalized")
    if result.get("signature") != signature:
        raise ValueError("Finalized signature mismatch")
    if result.get("transfer_verified") is not True:
        raise ValueError("Transfer verification failed")
    return result
