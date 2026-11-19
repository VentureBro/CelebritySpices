import json
import os
import urllib.request
import urllib.error

from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
import secrets

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import TokenAllocation, TokenWallet
from app.schemas import (
    TokenAllocationCreate,
    TokenWalletCreate,
)



admin_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


def require_token_admin(api_key: str | None = Security(admin_key_header)):
    expected = os.getenv("TOKEN_ADMIN_API_KEY")

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Token administrator authentication is not configured",
        )

    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing administrator API key",
        )

    return True


router = APIRouter(
    prefix="/token",
    tags=["Token"],
)

RPC_URL = os.getenv(
    "SOLANA_RPC_URL",
    "http://host.docker.internal:8899",
)

TOKEN_MINT = "55wALPPSEqNcpMRRQ33oMj7pBErH7eLgN2FTdgUtXuuE"
TREASURY_WALLET = "G1TpwMhcQJ5Kt2P594dimcJ6i1P11FuzCJwZkVEu5oUW"
TREASURY_TOKEN_ACCOUNT = "45ybNYUvzwMkPQ3qrSN3ALX2QsEkt6T2TxHU1Jw4crUN"

EXPECTED_SUPPLY = 10_000_000_000
DECIMALS = 2


def rpc_call(method: str, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or [],
    }

    request = urllib.request.Request(
        RPC_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Solana RPC unavailable: {exc}",
        ) from exc

    if "error" in result:
        raise HTTPException(
            status_code=502,
            detail=result["error"],
        )

    return result["result"]


@router.get("/status")
def token_status():
    version = rpc_call("getVersion")

    supply_result = rpc_call(
        "getTokenSupply",
        [TOKEN_MINT],
    )

    treasury_result = rpc_call(
        "getTokenAccountBalance",
        [TREASURY_TOKEN_ACCOUNT],
    )

    supply_value = supply_result["value"]
    treasury_value = treasury_result["value"]

    supply_base_units = int(supply_value["amount"])
    treasury_base_units = int(treasury_value["amount"])

    decimals = int(supply_value["decimals"])
    divisor = 10 ** decimals

    distributed_base_units = (
        supply_base_units - treasury_base_units
    )

    supply_tokens = supply_base_units // divisor
    treasury_tokens = treasury_base_units // divisor
    distributed_tokens = distributed_base_units // divisor

    return {
        "status": "healthy",
        "network": "private-localnet",
        "rpc": RPC_URL,
        "validator_version": version.get("solana-core"),
        "token": {
            "mint": TOKEN_MINT,
            "decimals": decimals,
            "supply_base_units": supply_base_units,
            "supply": supply_tokens,
            "expected_supply": EXPECTED_SUPPLY,
            "supply_matches": supply_tokens == EXPECTED_SUPPLY,
        },
        "treasury": {
            "wallet": TREASURY_WALLET,
            "token_account": TREASURY_TOKEN_ACCOUNT,
            "balance_base_units": treasury_base_units,
            "balance": treasury_tokens,
        },
        "distributed_base_units": distributed_base_units,
        "distributed": distributed_tokens,
    }


@router.get("/wallet/{wallet_address}")
def wallet_status(wallet_address: str):
    with SessionLocal() as db:
        wallet = db.execute(
            select(TokenWallet).where(
                TokenWallet.wallet_address == wallet_address
            )
        ).scalar_one_or_none()

        if wallet is None:
            raise HTTPException(
                status_code=404,
                detail="Token wallet not found",
            )

        allocated_base_units = db.execute(
            select(
                func.coalesce(
                    func.sum(TokenAllocation.amount_base_units),
                    0,
                )
            ).where(
                TokenAllocation.wallet_id == wallet.id,
                TokenAllocation.status == "confirmed",
            )
        ).scalar_one()

        allocated_base_units = int(allocated_base_units)

        if not wallet.token_account_address:
            raise HTTPException(
                status_code=409,
                detail="Wallet has no token account address",
            )

        chain_result = rpc_call(
            "getTokenAccountBalance",
            [wallet.token_account_address],
        )

        chain_value = chain_result["value"]

        blockchain_base_units = int(chain_value["amount"])
        decimals = int(chain_value["decimals"])

        divisor = 10 ** decimals

        return {
            "wallet": {
                "id": wallet.id,
                "wallet_address": wallet.wallet_address,
                "token_account_address": wallet.token_account_address,
                "wallet_type": wallet.wallet_type,
                "display_name": wallet.display_name,
                "status": wallet.status,
            },
            "postgres": {
                "confirmed_allocation_base_units": allocated_base_units,
                "confirmed_allocation_tokens": (
                    f"{allocated_base_units / divisor:.{decimals}f}"
                ),
            },
            "solana": {
                "balance_base_units": blockchain_base_units,
                "balance_tokens": chain_value["uiAmountString"],
                "decimals": decimals,
            },
            "reconciliation": {
                "difference_base_units": (
                    blockchain_base_units - allocated_base_units
                ),
                "matches": (
                    blockchain_base_units == allocated_base_units
                ),
            },
        }


@router.get("/wallets")
def list_token_wallets():
    with SessionLocal() as db:
        wallets = db.execute(
            select(TokenWallet).order_by(TokenWallet.id)
        ).scalars().all()

        return [
            {
                "id": wallet.id,
                "wallet_address": wallet.wallet_address,
                "token_account_address": wallet.token_account_address,
                "wallet_type": wallet.wallet_type,
                "display_name": wallet.display_name,
                "status": wallet.status,
                "created_at": wallet.created_at,
            }
            for wallet in wallets
        ]


@router.get("/allocations")
def list_token_allocations():
    with SessionLocal() as db:
        allocations = db.execute(
            select(TokenAllocation).order_by(TokenAllocation.id)
        ).scalars().all()

        return [
            {
                "id": allocation.id,
                "wallet_id": allocation.wallet_id,
                "amount_base_units": allocation.amount_base_units,
                "token_decimals": allocation.token_decimals,
                "token_amount": (
                    f"{allocation.amount_base_units / (10 ** allocation.token_decimals):.{allocation.token_decimals}f}"
                ),
                "allocation_type": allocation.allocation_type,
                "blockchain_signature": allocation.blockchain_signature,
                "status": allocation.status,
                "notes": allocation.notes,
                "created_at": allocation.created_at,
                "confirmed_at": allocation.confirmed_at,
            }
            for allocation in allocations
        ]


@router.post("/wallets", status_code=201)
def create_token_wallet(payload: TokenWalletCreate, admin=Depends(require_token_admin)):
    wallet_address = payload.wallet_address.strip()

    token_account_address = (
        payload.token_account_address.strip()
        if payload.token_account_address
        else None
    )

    wallet_type = payload.wallet_type.strip().lower()

    display_name = (
        payload.display_name.strip()
        if payload.display_name
        else None
    )

    if not wallet_address:
        raise HTTPException(
            status_code=422,
            detail="Wallet address is required",
        )

    if not wallet_type:
        raise HTTPException(
            status_code=422,
            detail="Wallet type is required",
        )

    # Ask the Solana validator to parse the submitted public key.
    # A valid public key does not need to have an existing account yet.
    try:
        rpc_call(
            "getAccountInfo",
            [
                wallet_address,
                {
                    "encoding": "base64",
                    "commitment": "confirmed",
                },
            ],
        )
    except HTTPException as exc:
        if exc.status_code == 502:
            raise HTTPException(
                status_code=422,
                detail="Invalid Solana wallet address",
            ) from exc
        raise

    if token_account_address:
        try:
            token_account_result = rpc_call(
                "getAccountInfo",
                [
                    token_account_address,
                    {
                        "encoding": "jsonParsed",
                        "commitment": "confirmed",
                    },
                ],
            )
        except HTTPException as exc:
            if exc.status_code == 502:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid Solana token account address",
                ) from exc
            raise

        token_account_info = token_account_result["value"]

        if token_account_info is None:
            raise HTTPException(
                status_code=422,
                detail="Token account does not exist",
            )

        parsed = (
            token_account_info
            .get("data", {})
            .get("parsed", {})
        )

        info = parsed.get("info", {})

        if info.get("mint") != TOKEN_MINT:
            raise HTTPException(
                status_code=422,
                detail="Token account belongs to a different mint",
            )

        if info.get("owner") != wallet_address:
            raise HTTPException(
                status_code=422,
                detail="Token account does not belong to wallet",
            )

    with SessionLocal() as db:
        existing = db.execute(
            select(TokenWallet).where(
                TokenWallet.wallet_address == wallet_address
            )
        ).scalar_one_or_none()

        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="Wallet already registered",
            )

        if token_account_address:
            existing_token_account = db.execute(
                select(TokenWallet).where(
                    TokenWallet.token_account_address
                    == token_account_address
                )
            ).scalar_one_or_none()

            if existing_token_account is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Token account already registered",
                )

        wallet = TokenWallet(
            wallet_address=wallet_address,
            token_account_address=token_account_address,
            wallet_type=wallet_type,
            display_name=display_name,
            status="active",
        )

        db.add(wallet)
        db.commit()
        db.refresh(wallet)

        return {
            "id": wallet.id,
            "wallet_address": wallet.wallet_address,
            "token_account_address": wallet.token_account_address,
            "wallet_type": wallet.wallet_type,
            "display_name": wallet.display_name,
            "status": wallet.status,
            "created_at": wallet.created_at,
            "updated_at": wallet.updated_at,
        }


@router.post("/allocations", status_code=201)
def create_token_allocation(payload: TokenAllocationCreate, admin=Depends(require_token_admin)):
    allocation_type = payload.allocation_type.strip().lower()

    notes = (
        payload.notes.strip()
        if payload.notes
        else None
    )

    if not allocation_type:
        raise HTTPException(
            status_code=422,
            detail="Allocation type is required",
        )

    amount_base_units = (
        payload.amount_tokens * (10 ** DECIMALS)
    )

    with SessionLocal() as db:
        wallet = db.execute(
            select(TokenWallet).where(
                TokenWallet.id == payload.wallet_id
            )
        ).scalar_one_or_none()

        if wallet is None:
            raise HTTPException(
                status_code=404,
                detail="Token wallet not found",
            )

        if wallet.status != "active":
            raise HTTPException(
                status_code=409,
                detail="Token wallet is not active",
            )

        if not wallet.token_account_address:
            raise HTTPException(
                status_code=409,
                detail="Wallet has no token account address",
            )

        allocation = TokenAllocation(
            wallet_id=wallet.id,
            amount_base_units=amount_base_units,
            token_decimals=DECIMALS,
            allocation_type=allocation_type,
            blockchain_signature=None,
            status="pending",
            notes=notes,
        )

        db.add(allocation)
        db.commit()
        db.refresh(allocation)

        return {
            "id": allocation.id,
            "wallet_id": allocation.wallet_id,
            "amount_base_units": allocation.amount_base_units,
            "token_decimals": allocation.token_decimals,
            "amount_tokens": (
                allocation.amount_base_units
                // (10 ** allocation.token_decimals)
            ),
            "allocation_type": allocation.allocation_type,
            "blockchain_signature": allocation.blockchain_signature,
            "status": allocation.status,
            "notes": allocation.notes,
            "created_at": allocation.created_at,
            "confirmed_at": allocation.confirmed_at,
        }

@router.post("/allocations/{allocation_id}/approve")
def approve_token_allocation(allocation_id: int, admin=Depends(require_token_admin)):
    with SessionLocal() as db:
        allocation = db.execute(
            select(TokenAllocation).where(
                TokenAllocation.id == allocation_id
            )
        ).scalar_one_or_none()

        if allocation is None:
            raise HTTPException(
                status_code=404,
                detail="Token allocation not found",
            )

        if allocation.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Allocation cannot be approved "
                    f"from status '{allocation.status}'"
                ),
            )

        if allocation.blockchain_signature is not None:
            raise HTTPException(
                status_code=409,
                detail="Pending allocation already has a blockchain signature",
            )

        wallet = db.execute(
            select(TokenWallet).where(
                TokenWallet.id == allocation.wallet_id
            )
        ).scalar_one_or_none()

        if wallet is None:
            raise HTTPException(
                status_code=404,
                detail="Token wallet not found",
            )

        if wallet.status != "active":
            raise HTTPException(
                status_code=409,
                detail="Token wallet is not active",
            )

        if not wallet.token_account_address:
            raise HTTPException(
                status_code=409,
                detail="Wallet has no token account address",
            )

        allocation.status = "approved"

        db.commit()
        db.refresh(allocation)

        return {
            "id": allocation.id,
            "wallet_id": allocation.wallet_id,
            "amount_base_units": allocation.amount_base_units,
            "token_decimals": allocation.token_decimals,
            "token_amount": (
                f"{allocation.amount_base_units / (10 ** allocation.token_decimals):.2f}"
            ),
            "allocation_type": allocation.allocation_type,
            "blockchain_signature": allocation.blockchain_signature,
            "status": allocation.status,
            "notes": allocation.notes,
            "created_at": allocation.created_at,
            "confirmed_at": allocation.confirmed_at,
        }
