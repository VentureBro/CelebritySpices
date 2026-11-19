import json
import sys
import urllib.request

from preflight import (
    TOKEN_DECIMALS,
    TOKEN_MINT,
    TREASURY_TOKEN_ACCOUNT,
    TREASURY_WALLET,
    load_allocation,
)


RPC_URL = "http://127.0.0.1:8899"
EXPECTED_GENESIS = (
    "GfXab63AGhLWd9okAE94cvwo9dJi7pf7rQ391KwnxaBt"
)


def rpc(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }

    if params is not None:
        payload["params"] = params

    request = urllib.request.Request(
        RPC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=5,
    ) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    if "error" in result:
        raise RuntimeError(
            json.dumps(result["error"])
        )

    return result["result"]


def token_account(address):
    result = rpc(
        "getAccountInfo",
        [
            address,
            {
                "encoding": "jsonParsed",
            },
        ],
    )

    value = result["value"]

    if value is None:
        raise RuntimeError(
            f"Token account not found: {address}"
        )

    if value["owner"] != (
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    ):
        raise RuntimeError(
            "Account is not owned by the SPL Token program"
        )

    parsed = value["data"]["parsed"]

    if parsed["type"] != "account":
        raise RuntimeError(
            "Account is not an SPL token account"
        )

    return parsed["info"]


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: chain_check.py <allocation_id>"
        )

    allocation_id = int(sys.argv[1])
    allocation = load_allocation(allocation_id)

    if allocation is None:
        raise RuntimeError(
            f"Allocation #{allocation_id} not found"
        )

    if allocation["status"] != "approved":
        raise RuntimeError(
            f"Allocation #{allocation_id} is not approved"
        )

    if allocation["blockchain_signature"] is not None:
        raise RuntimeError(
            f"Allocation #{allocation_id} already has a signature"
        )

    genesis = rpc("getGenesisHash")

    if genesis != EXPECTED_GENESIS:
        raise RuntimeError(
            f"Wrong Solana genesis: {genesis}"
        )

    treasury = token_account(
        TREASURY_TOKEN_ACCOUNT
    )

    destination = token_account(
        allocation["token_account_address"]
    )

    if treasury["mint"] != TOKEN_MINT:
        raise RuntimeError(
            "Treasury token account has wrong mint"
        )

    if treasury["owner"] != TREASURY_WALLET:
        raise RuntimeError(
            "Treasury token account has wrong owner"
        )

    if destination["mint"] != TOKEN_MINT:
        raise RuntimeError(
            "Destination token account has wrong mint"
        )

    if destination["owner"] != allocation["wallet_address"]:
        raise RuntimeError(
            "Destination token account has wrong owner"
        )

    if treasury["state"] != "initialized":
        raise RuntimeError(
            "Treasury token account is not initialized"
        )

    if destination["state"] != "initialized":
        raise RuntimeError(
            "Destination token account is not initialized"
        )

    treasury_amount = int(
        treasury["tokenAmount"]["amount"]
    )

    destination_amount = int(
        destination["tokenAmount"]["amount"]
    )

    amount = int(
        allocation["amount_base_units"]
    )

    if treasury_amount < amount:
        raise RuntimeError(
            "Treasury has insufficient token balance"
        )

    if int(
        treasury["tokenAmount"]["decimals"]
    ) != TOKEN_DECIMALS:
        raise RuntimeError(
            "Treasury decimals mismatch"
        )

    if int(
        destination["tokenAmount"]["decimals"]
    ) != TOKEN_DECIMALS:
        raise RuntimeError(
            "Destination decimals mismatch"
        )

    print("===== LIVE CHAIN PREFLIGHT =====")
    print("Genesis:", genesis)
    print("Allocation:", allocation["id"])
    print("Status:", allocation["status"])
    print("Mint:", TOKEN_MINT)
    print(
        "Treasury balance base units:",
        treasury_amount,
    )
    print(
        "Destination balance base units:",
        destination_amount,
    )
    print(
        "Transfer base units:",
        amount,
    )
    print()
    print("CHAIN PREFLIGHT: PASS")
    print("NO TRANSACTION HAS BEEN SIGNED OR SENT")


if __name__ == "__main__":
    main()
