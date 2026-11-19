import struct

from solders.pubkey import Pubkey
from solders.transaction import Transaction

TOKEN_PROGRAM = Pubkey.from_string(
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
)


def validate_token_transfer(
    signed_transaction,
    expected_authority,
    expected_source,
    expected_destination,
    expected_mint,
    expected_amount,
    expected_decimals,
):
    transaction = Transaction.from_bytes(
        signed_transaction
    )

    transaction.verify()

    message = transaction.message

    if len(transaction.signatures) != 1:
        raise ValueError("Expected exactly one signature")

    if message.header.num_required_signatures != 1:
        raise ValueError("Expected exactly one signer")

    if len(message.instructions) != 1:
        raise ValueError("Expected exactly one instruction")

    keys = message.account_keys

    if str(keys[0]) != str(expected_authority):
        raise ValueError("Unexpected signing authority")

    instruction = message.instructions[0]

    if keys[instruction.program_id_index] != TOKEN_PROGRAM:
        raise ValueError("Unexpected token program")

    if len(instruction.accounts) != 4:
        raise ValueError("Unexpected instruction accounts")

    accounts = [
        str(keys[index])
        for index in instruction.accounts
    ]

    expected_accounts = [
        str(expected_source),
        str(expected_mint),
        str(expected_destination),
        str(expected_authority),
    ]

    if accounts != expected_accounts:
        raise ValueError("Token accounts do not match")

    header = message.header

    required_signatures = header.num_required_signatures
    readonly_signed = header.num_readonly_signed_accounts
    readonly_unsigned = header.num_readonly_unsigned_accounts

    def is_writable(index):
        if index < required_signatures:
            return index < (
                required_signatures - readonly_signed
            )

        return index < (
            len(keys) - readonly_unsigned
        )

    source_index, mint_index, destination_index, authority_index = (
        instruction.accounts
    )

    if not is_writable(source_index):
        raise ValueError("Source token account must be writable")

    if not is_writable(destination_index):
        raise ValueError("Destination token account must be writable")

    if is_writable(mint_index):
        raise ValueError("Mint account must be read-only")

    if authority_index != 0:
        raise ValueError("Unexpected authority signer index")

    data = bytes(instruction.data)

    if len(data) != 10:
        raise ValueError("Unexpected instruction data length")

    instruction_type, amount, decimals = struct.unpack(
        "<BQB",
        data,
    )

    if instruction_type != 12:
        raise ValueError("Not a TransferChecked instruction")

    if amount <= 0 or amount != expected_amount:
        raise ValueError("Transfer amount mismatch")

    if decimals != expected_decimals:
        raise ValueError("Token decimals mismatch")

    return True
