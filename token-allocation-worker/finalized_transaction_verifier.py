import base64
import binascii

from solders.transaction import Transaction
from finalized_transaction_rpc import get_finalized_transaction
from token_instruction_validator import validate_token_transfer


def verify_finalized_transfer(
    signed_transaction,
    expected_signature,
    expected_authority,
    expected_source,
    expected_destination,
    expected_mint,
    expected_amount,
    expected_decimals,
):
    if not isinstance(signed_transaction, bytes):
        raise ValueError("Signed transaction bytes required")

    original = Transaction.from_bytes(signed_transaction)
    original.verify()

    if str(original.signatures[0]) != expected_signature:
        raise ValueError("Original signature mismatch")

    validate_token_transfer(
        signed_transaction,
        expected_authority,
        expected_source,
        expected_destination,
        expected_mint,
        expected_amount,
        expected_decimals,
    )

    result = get_finalized_transaction(expected_signature)

    try:
        encoded = result["transaction"][0]
        finalized_bytes = base64.b64decode(
            encoded, validate=True
        )
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error):
        raise ValueError("Invalid finalized transaction data")

    if finalized_bytes != signed_transaction:
        raise ValueError("Finalized transaction does not match journal")

    finalized = Transaction.from_bytes(finalized_bytes)
    finalized.verify()

    if str(finalized.signatures[0]) != expected_signature:
        raise ValueError("Finalized signature mismatch")

    return {
        "classification": "FINALIZED_SUCCESS",
        "signature": expected_signature,
        "transfer_verified": True,
    }
