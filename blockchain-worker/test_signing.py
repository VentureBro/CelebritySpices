import base64
import json
import struct
import urllib.request
from pathlib import Path

from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction


RPC_URL = "http://127.0.0.1:8899"

PROGRAM_ID = Pubkey.from_string(
    "Af1raDw63K9whsXG6CGUBxcpGmSLQf8jzEcEay3zLT4z"
)

SYSTEM_PROGRAM = Pubkey.from_string(
    "11111111111111111111111111111111"
)

ANCHOR_DISCRIMINATOR = bytes([
    133, 236, 129, 214,
    222, 66, 139, 144,
])

KEYPAIR_PATH = Path(
    "../secrets/solana-audit-authority.json"
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
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=10,
    ) as response:
        result = json.loads(
            response.read().decode()
        )

    if "error" in result:
        raise RuntimeError(result["error"])

    return result["result"]


def load_keypair():
    raw = json.loads(
        KEYPAIR_PATH.read_text()
    )

    return Keypair.from_bytes(
        bytes(raw)
    )


def main():
    signer = load_keypair()

    # Use movement #30 only to test construction.
    # This transaction WILL NOT be submitted.
    movement_id = 30
    inventory_item_id = 4
    quantity_change = -1
    quantity_before = 103
    quantity_after = 102

    audit_hash = bytes.fromhex(
        "d0e353096d34cefe149ab4b2ef49bbe8"
        "928b0ea59c3c21bbee71de8fb18e2de2"
    )

    movement_seed = movement_id.to_bytes(
        8,
        byteorder="little",
        signed=False,
    )

    audit_pda, bump = (
        Pubkey.find_program_address(
            [
                b"inventory-audit",
                movement_seed,
            ],
            PROGRAM_ID,
        )
    )

    data = (
        ANCHOR_DISCRIMINATOR
        + struct.pack("<Q", movement_id)
        + struct.pack("<Q", inventory_item_id)
        + struct.pack("<q", quantity_change)
        + struct.pack("<q", quantity_before)
        + struct.pack("<q", quantity_after)
        + audit_hash
    )

    instruction = Instruction(
        PROGRAM_ID,
        data,
        [
            AccountMeta(
                signer.pubkey(),
                True,
                True,
            ),
            AccountMeta(
                audit_pda,
                False,
                True,
            ),
            AccountMeta(
                SYSTEM_PROGRAM,
                False,
                False,
            ),
        ],
    )

    latest = rpc(
        "getLatestBlockhash",
        [{"commitment": "confirmed"}],
    )

    blockhash_string = (
        latest["value"]["blockhash"]
    )

    blockhash = Hash.from_string(
        blockhash_string
    )

    transaction = (
        Transaction.new_signed_with_payer(
            [instruction],
            signer.pubkey(),
            [signer],
            blockhash,
        )
    )

    raw_transaction = bytes(transaction)
    encoded = base64.b64encode(
        raw_transaction
    ).decode()

    print(
        "===== SOLANA SIGNING DRY RUN ====="
    )
    print("Signer:", signer.pubkey())
    print("Program:", PROGRAM_ID)
    print("Movement:", movement_id)
    print("Audit PDA:", audit_pda)
    print("PDA bump:", bump)
    print("Instruction bytes:", len(data))
    print("Recent blockhash:", blockhash)
    print(
        "Serialized transaction bytes:",
        len(raw_transaction),
    )
    print(
        "Base64 transaction length:",
        len(encoded),
    )

    print()
    print("Transaction signed: OK")
    print("Transaction broadcast: NO")


if __name__ == "__main__":
    main()
