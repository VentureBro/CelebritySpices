import json
import urllib.request
from solders.signature import Signature


RPC_URL = "http://127.0.0.1:8899"


def rpc_request(method, params=None):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or [],
    }).encode("utf-8")

    request = urllib.request.Request(
        RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=10,
    ) as response:
        result = json.load(response)

    if "error" in result:
        raise RuntimeError(
            f"Solana RPC error: {result['error']}"
        )

    return result["result"]


def get_transaction_status(signature):
    # Reject malformed signatures before making RPC requests.
    Signature.from_string(signature)

    result = rpc_request(
        "getSignatureStatuses",
        [
            [signature],
            {"searchTransactionHistory": True},
        ],
    )

    status = result["value"][0]

    if status is None:
        return {
            "classification": "NOT_FOUND_REQUIRES_RECONCILIATION",
            "status": None,
        }

    if status.get("err") is not None:
        return {
            "classification": "TRANSACTION_FAILED",
            "status": status,
        }

    confirmation = status.get("confirmationStatus")

    if confirmation == "finalized":
        classification = "FINALIZED_SUCCESS"
    elif confirmation == "confirmed":
        classification = "CONFIRMED_NOT_FINALIZED"
    else:
        classification = "PENDING_OR_UNCONFIRMED"

    return {
        "classification": classification,
        "status": status,
    }


def get_current_block_height():
    return rpc_request(
        "getBlockHeight",
        [{"commitment": "confirmed"}],
    )


def inspect_signed_transaction(
    signature,
    last_valid_block_height,
):
    if (
        not isinstance(last_valid_block_height, int)
        or isinstance(last_valid_block_height, bool)
        or last_valid_block_height <= 0
    ):
        raise ValueError(
            "Invalid last valid block height"
        )

    transaction = get_transaction_status(signature)
    current_height = get_current_block_height()

    expired = current_height > last_valid_block_height

    return {
        "signature": signature,
        "classification": transaction["classification"],
        "current_block_height": current_height,
        "last_valid_block_height": last_valid_block_height,
        "blockhash_height_exceeded": expired,
        "requires_reconciliation": (
            transaction["classification"]
            != "FINALIZED_SUCCESS"
        ),
    }
