"""Journal-first broadcaster; disabled by default."""

from journal_integration_adapter import journal_prepared_transfer


def broadcast_journaled_transfer(
    allocation_id,
    prepared,
    journal_function,
    broadcast_function,
    *,
    enable_broadcast=False,
):
    if enable_broadcast is not True:
        raise RuntimeError("SAFETY LOCK: Broadcasting disabled")

    signature = journal_prepared_transfer(
        allocation_id, prepared, journal_function
    )

    if signature != prepared["signature"]:
        raise RuntimeError("Journal signature mismatch")

    return broadcast_function(prepared["signed_transaction"])
