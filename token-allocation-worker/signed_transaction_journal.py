from solders.transaction import Transaction
from preflight import (
    TOKEN_MINT,
    TOKEN_DECIMALS,
    TREASURY_WALLET,
    TREASURY_TOKEN_ACCOUNT,
)
from token_instruction_validator import validate_token_transfer

from preflight import database_connection


def persist_signed_transaction(
    allocation_id,
    signed_transaction,
    signature,
    recent_blockhash,
    last_valid_block_height,
):
    if not isinstance(signed_transaction, bytes):
        raise ValueError("Signed transaction must be bytes")

    if not signed_transaction:
        raise ValueError("Signed transaction cannot be empty")

    transaction = Transaction.from_bytes(signed_transaction)

    try:
        transaction.verify()
    except Exception as exc:
        raise ValueError(
            "Cryptographic transaction verification failed"
        ) from exc

    if len(transaction.signatures) != 1:
        raise ValueError("Expected exactly one transaction signature")

    actual_signature = str(transaction.signatures[0])

    if actual_signature != signature:
        raise ValueError("Transaction signature mismatch")

    if str(transaction.message.recent_blockhash) != recent_blockhash:
        raise ValueError("Transaction blockhash mismatch")

    if not isinstance(last_valid_block_height, int):
        raise ValueError("Invalid last valid block height")

    if last_valid_block_height <= 0:
        raise ValueError("Invalid last valid block height")

    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.status AS allocation_status,
                    a.blockchain_signature,
                    a.amount_base_units AS allocation_amount,
                    a.token_decimals,
                    w.token_account_address,
                    w.status AS wallet_status,
                    t.status AS journal_status,
                    t.destination_token_account,
                    t.amount_base_units AS journal_amount
                FROM token_transfer_attempts t
                JOIN token_allocations a
                  ON a.id = t.allocation_id
                JOIN token_wallets w
                  ON w.id = a.wallet_id
                WHERE t.allocation_id = %s
                FOR UPDATE OF t, a, w
                """,
                (allocation_id,),
            )

            record = cur.fetchone()

            if record is None:
                raise ValueError("Reserved allocation not found")

            if record["allocation_status"] != "processing":
                raise ValueError("Allocation is not processing")

            if record["blockchain_signature"] is not None:
                raise ValueError("Allocation already has a signature")

            if record["journal_status"] != "reserved":
                raise ValueError("Journal is not reserved")

            if record["wallet_status"] != "active":
                raise ValueError("Destination wallet is not active")

            if record["token_decimals"] != TOKEN_DECIMALS:
                raise ValueError("Allocation decimals mismatch")

            if record["allocation_amount"] <= 0:
                raise ValueError("Invalid allocation amount")

            if record["allocation_amount"] != record["journal_amount"]:
                raise ValueError("Journal amount mismatch")

            if (
                record["token_account_address"]
                != record["destination_token_account"]
            ):
                raise ValueError("Journal destination mismatch")

            validate_token_transfer(
                signed_transaction,
                expected_authority=TREASURY_WALLET,
                expected_source=TREASURY_TOKEN_ACCOUNT,
                expected_destination=record["destination_token_account"],
                expected_mint=TOKEN_MINT,
                expected_amount=record["allocation_amount"],
                expected_decimals=TOKEN_DECIMALS,
            )

            cur.execute(
                """
                UPDATE token_transfer_attempts
                SET
                    signed_transaction = %s,
                    transaction_signature = %s,
                    recent_blockhash = %s,
                    last_valid_block_height = %s,
                    updated_at = NOW()
                WHERE allocation_id = %s
                  AND status = 'reserved'
                  AND transaction_signature IS NULL
                  AND signed_transaction IS NULL
                """,
                (
                    signed_transaction,
                    signature,
                    recent_blockhash,
                    last_valid_block_height,
                    allocation_id,
                ),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Signed transaction could not be persisted"
                )

        conn.commit()

    return signature
