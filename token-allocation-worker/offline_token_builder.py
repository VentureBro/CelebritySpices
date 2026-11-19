"""Offline SPL Token TransferChecked instruction builder."""
from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from solders.token import ID as TOKEN_PROGRAM_ID

def build_transfer_checked_instruction(source_token_account, destination_token_account, mint, authority, amount, decimals):
    if type(amount) is not int or not 0 < amount < 2**64:
        raise ValueError("Amount must be a positive u64 integer")
    if type(decimals) is not int or not 0 <= decimals <= 255:
        raise ValueError("Decimals must fit in u8")
    source = Pubkey.from_string(source_token_account)
    destination = Pubkey.from_string(destination_token_account)
    mint_key = Pubkey.from_string(mint)
    authority_key = Pubkey.from_string(authority)
    data = bytes([12]) + amount.to_bytes(8, "little") + bytes([decimals])
    accounts = [
        AccountMeta(source, False, True),
        AccountMeta(mint_key, False, False),
        AccountMeta(destination, False, True),
        AccountMeta(authority_key, True, False),
    ]
    return Instruction(TOKEN_PROGRAM_ID, data, accounts)
