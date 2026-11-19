from solders.signature import Signature
from solana_recovery_rpc import rpc_request


def get_finalized_transaction(signature):
    Signature.from_string(signature)

    result = rpc_request(
        "getTransaction",
        [
            signature,
            {
                "encoding": "base64",
                "commitment": "finalized",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    )

    if result is None:
        raise RuntimeError(
            "Finalized transaction not available"
        )

    if not isinstance(result, dict):
        raise RuntimeError(
            "Unexpected transaction RPC response"
        )

    meta = result.get("meta")

    if not isinstance(meta, dict):
        raise RuntimeError(
            "Transaction metadata missing"
        )

    if meta.get("err") is not None:
        raise RuntimeError(
            "Finalized transaction execution failed"
        )

    transaction = result.get("transaction")

    if (
        not isinstance(transaction, list)
        or len(transaction) != 2
        or not isinstance(transaction[0], str)
        or transaction[1] != "base64"
    ):
        raise RuntimeError(
            "Unexpected transaction encoding"
        )

    return result
