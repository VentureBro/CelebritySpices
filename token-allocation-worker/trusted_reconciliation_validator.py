"""Validate journal-backed reconciliation records without database writes."""
from solders.transaction import Transaction
from preflight import TOKEN_MINT, TOKEN_DECIMALS, TREASURY_WALLET, TREASURY_TOKEN_ACCOUNT
from token_instruction_validator import validate_token_transfer

def validate_reconciliation_record(record):
    if record is None:
        raise ValueError("Allocation not found")
    if record["allocation_status"] != "processing":
        raise ValueError("Allocation is not processing")
    if record["blockchain_signature"] is not None:
        raise ValueError("Allocation already confirmed")
    if record["wallet_status"] != "active":
        raise ValueError("Destination wallet inactive")
    if record["journal_status"] not in ("broadcasting", "submitted", "requires_reconciliation"):
        raise ValueError("Journal status not eligible")
    if type(record["allocation_amount"]) is not int or record["allocation_amount"] <= 0:
        raise ValueError("Invalid allocation amount")
    if record["allocation_amount"] != record["journal_amount"]:
        raise ValueError("Journal amount mismatch")
    if record["token_decimals"] != TOKEN_DECIMALS:
        raise ValueError("Token decimals mismatch")
    if record["token_account_address"] != record["destination_token_account"]:
        raise ValueError("Destination account mismatch")
    signed = record["signed_transaction"]
    if isinstance(signed, memoryview):
        signed = signed.tobytes()
    if not isinstance(signed, bytes) or not signed:
        raise ValueError("Missing signed transaction")
    signature = record["transaction_signature"]
    if not isinstance(signature, str) or not signature:
        raise ValueError("Missing transaction signature")
    transaction = Transaction.from_bytes(signed)
    transaction.verify()
    if len(transaction.signatures) != 1 or str(transaction.signatures[0]) != signature:
        raise ValueError("Signature mismatch")
    if str(transaction.message.recent_blockhash) != record["recent_blockhash"]:
        raise ValueError("Blockhash mismatch")
    if type(record["last_valid_block_height"]) is not int or record["last_valid_block_height"] <= 0:
        raise ValueError("Invalid block height")
    validate_token_transfer(signed, TREASURY_WALLET, TREASURY_TOKEN_ACCOUNT, record["destination_token_account"], TOKEN_MINT, record["allocation_amount"], TOKEN_DECIMALS)
    return signed, signature
