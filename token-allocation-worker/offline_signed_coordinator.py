"""Offline signed SPL Token transaction preparation."""
from solders.hash import Hash
from solders.transaction import Transaction
from offline_token_builder import build_transfer_checked_instruction
from token_instruction_validator import validate_token_transfer

def prepare_signed_transfer(authority_keypair, source, destination, mint, amount, decimals, recent_blockhash, last_valid_block_height):
    if type(last_valid_block_height) is not int or last_valid_block_height <= 0:
        raise ValueError("Invalid last valid block height")
    authority = str(authority_keypair.pubkey())
    instruction = build_transfer_checked_instruction(source, destination, mint, authority, amount, decimals)
    transaction = Transaction.new_signed_with_payer(
        [instruction], authority_keypair.pubkey(), [authority_keypair], Hash.from_string(recent_blockhash)
    )
    signed_bytes = bytes(transaction)
    validate_token_transfer(signed_bytes, authority, source, destination, mint, amount, decimals)
    signature = str(transaction.signatures[0])
    return {
        "signed_transaction": signed_bytes,
        "signature": signature,
        "recent_blockhash": recent_blockhash,
        "last_valid_block_height": last_valid_block_height,
    }
