from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_code: str
    name: str
    city: str | None
    province: str | None
    country_code: str
    shopify_location_id: str | None
    is_active: bool


class InventoryLevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int
    on_hand_quantity: int
    committed_quantity: int
    incoming_quantity: int
    reserved_quantity: int
    reorder_point: int
    reorder_quantity: int
    shopify_available_quantity: int | None


class InventoryItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    barcode: str | None = Field(default=None, max_length=100)
    unit_of_measure: str = Field(default="each", max_length=30)

    warehouse_id: int = Field(gt=0)
    initial_quantity: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=0, ge=0)
    reorder_quantity: int = Field(default=0, ge=0)

    shopify_product_id: str | None = None
    shopify_variant_id: str | None = None
    shopify_inventory_item_id: str | None = None


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str | None
    barcode: str | None
    unit_of_measure: str

    shopify_product_id: str | None
    shopify_variant_id: str | None
    shopify_inventory_item_id: str | None

    tracks_inventory: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    inventory_levels: list[InventoryLevelResponse] = []


class ReceivingCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0)
    warehouse_code: str = Field(default="MAIN", min_length=1, max_length=50)
    reference_id: str | None = Field(default=None, max_length=150)
    notes: str | None = None


class InventoryMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inventory_item_id: int
    warehouse_id: int
    movement_type: str
    quantity_change: int
    quantity_before: int
    quantity_after: int
    reference_type: str | None
    reference_id: str | None
    notes: str | None
    source_system: str
    created_at: datetime


class ShippingCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0)
    warehouse_code: str = Field(default="MAIN", min_length=1, max_length=50)
    reference_id: str | None = Field(default=None, max_length=150)
    notes: str | None = None


class InventoryAdjustmentCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    adjustment_type: str = Field(min_length=1, max_length=30)
    quantity: int = Field(ge=0)
    warehouse_code: str = Field(default="MAIN", min_length=1, max_length=50)
    reference_id: str | None = Field(default=None, max_length=150)
    notes: str | None = None


class TokenAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wallet_id: int
    amount_base_units: int
    token_decimals: int
    allocation_type: str
    blockchain_signature: str | None
    status: str
    notes: str | None
    created_at: datetime
    confirmed_at: datetime | None


class TokenWalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wallet_address: str
    token_account_address: str | None
    wallet_type: str
    display_name: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    allocations: list[TokenAllocationResponse] = []


class TokenWalletCreate(BaseModel):
    wallet_address: str = Field(min_length=32, max_length=44)
    token_account_address: str | None = Field(
        default=None,
        min_length=32,
        max_length=44,
    )
    wallet_type: str = Field(
        default="influencer",
        min_length=1,
        max_length=30,
    )
    display_name: str | None = Field(
        default=None,
        max_length=200,
    )


class TokenAllocationCreate(BaseModel):
    wallet_id: int = Field(gt=0)
    amount_tokens: int = Field(gt=0)
    allocation_type: str = Field(
        default="standard",
        min_length=1,
        max_length=40,
    )
    notes: str | None = None
