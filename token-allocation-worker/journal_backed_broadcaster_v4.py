"""Journal-backed broadcaster V4; offline testing only."""

from journal_integration_adapter import journal_prepared_transfer
from broadcast_journal_verifier import verify_broadcast_ready


def broadcast_journaled_transfer_v4(
    allocation_id,
    prepared,
    journal_function,
    broadcasting_transition,
    submitted_transition,
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

    broadcasting_transition(allocation_id, signature)

    if verify_broadcast_ready(allocation_id, prepared) is not True:
        raise RuntimeError("Committed journal verification failed")

    result = broadcast_function(prepared["signed_transaction"])

    if result != signature:
        raise RuntimeError("Broadcast signature mismatch or unverified response")

    submitted_transition(allocation_id, signature)

    return signature
