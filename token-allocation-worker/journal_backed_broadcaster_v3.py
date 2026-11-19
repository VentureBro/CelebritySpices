"""Journal-backed broadcaster V3; disabled by default."""

from journal_integration_adapter import journal_prepared_transfer
from broadcast_journal_verifier import verify_broadcast_ready


def broadcast_journaled_transfer_v3(
    allocation_id,
    prepared,
    journal_function,
    transition_function,
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

    transition_function(allocation_id, signature)

    if verify_broadcast_ready(allocation_id, prepared) is not True:
        raise RuntimeError("Committed journal verification failed")

    return broadcast_function(prepared["signed_transaction"])
