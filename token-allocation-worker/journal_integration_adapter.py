"""Journal adapter for prepared signed SPL Token transactions."""

REQUIRED_FIELDS = (
    "signed_transaction",
    "signature",
    "recent_blockhash",
    "last_valid_block_height",
)

def journal_prepared_transfer(allocation_id, prepared, journal_function):
    if type(allocation_id) is not int or allocation_id <= 0:
        raise ValueError("Invalid allocation ID")
    if not isinstance(prepared, dict):
        raise TypeError("Prepared transaction must be a dictionary")
    if not callable(journal_function):
        raise TypeError("Journal function must be callable")
    for field in REQUIRED_FIELDS:
        if field not in prepared:
            raise ValueError("Missing journal field: " + field)
    return journal_function(
        allocation_id=allocation_id,
        signed_transaction=prepared["signed_transaction"],
        signature=prepared["signature"],
        recent_blockhash=prepared["recent_blockhash"],
        last_valid_block_height=prepared["last_valid_block_height"],
    )
