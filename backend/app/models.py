from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    warehouse_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    address_line_1: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(100))
    country_code: Mapped[str] = mapped_column(String(2), default="CA")
    shopify_location_id: Mapped[str | None] = mapped_column(
        String(150),
        unique=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    inventory_levels: Mapped[list["InventoryLevel"]] = relationship(
        back_populates="warehouse"
    )


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    barcode: Mapped[str | None] = mapped_column(String(100))
    unit_of_measure: Mapped[str] = mapped_column(String(30), default="each")

    shopify_product_id: Mapped[str | None] = mapped_column(String(150))
    shopify_variant_id: Mapped[str | None] = mapped_column(
        String(150),
        unique=True,
    )
    shopify_inventory_item_id: Mapped[str | None] = mapped_column(
        String(150),
        unique=True,
    )

    tracks_inventory: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_shopify_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    inventory_levels: Mapped[list["InventoryLevel"]] = relationship(
        back_populates="inventory_item"
    )


class InventoryLevel(Base):
    __tablename__ = "inventory_levels"
    __table_args__ = (
        UniqueConstraint(
            "inventory_item_id",
            "warehouse_id",
            name="inventory_levels_item_warehouse_unique",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"),
        nullable=False,
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=False,
    )

    on_hand_quantity: Mapped[int] = mapped_column(Integer, default=0)
    committed_quantity: Mapped[int] = mapped_column(Integer, default=0)
    incoming_quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)

    reorder_point: Mapped[int] = mapped_column(Integer, default=0)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=0)

    shopify_available_quantity: Mapped[int | None] = mapped_column(Integer)
    last_shopify_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    inventory_item: Mapped["InventoryItem"] = relationship(
        back_populates="inventory_levels"
    )
    warehouse: Mapped["Warehouse"] = relationship(
        back_populates="inventory_levels"
    )


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"),
        nullable=False,
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=False,
    )

    movement_type: Mapped[str] = mapped_column(String(40))
    quantity_change: Mapped[int] = mapped_column(Integer)
    quantity_before: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)

    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str] = mapped_column(
        String(30),
        default="operations-platform",
    )

    employee_id: Mapped[int | None] = mapped_column(BigInteger)
    blockchain_signature: Mapped[str | None] = mapped_column(String(150))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    shopify_order_id: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
    )
    shopify_order_name: Mapped[str | None] = mapped_column(String(100))

    financial_status: Mapped[str | None] = mapped_column(String(50))
    fulfillment_status: Mapped[str | None] = mapped_column(String(50))
    customer_name: Mapped[str | None] = mapped_column(String(200))

    operational_status: Mapped[str] = mapped_column(
        String(50),
        default="new",
        nullable=False,
    )

    shopify_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    shopify_line_item_id: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
    )

    sku: Mapped[str | None] = mapped_column(String(100))
    product_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    current_quantity: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    shopify_variant_id: Mapped[str | None] = mapped_column(String(150))

    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    order: Mapped["Order"] = relationship(
        back_populates="items"
    )


class TokenWallet(Base):
    __tablename__ = "token_wallets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    wallet_address: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    token_account_address: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
    )

    wallet_type: Mapped[str] = mapped_column(
        String(30),
        default="influencer",
        nullable=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(200))

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    allocations: Mapped[list["TokenAllocation"]] = relationship(
        back_populates="wallet",
    )


class TokenAllocation(Base):
    __tablename__ = "token_allocations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("token_wallets.id", ondelete="RESTRICT"),
        nullable=False,
    )

    amount_base_units: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    token_decimals: Mapped[int] = mapped_column(
        Integer,
        default=2,
        nullable=False,
    )

    allocation_type: Mapped[str] = mapped_column(
        String(40),
        default="standard",
        nullable=False,
    )

    blockchain_signature: Mapped[str | None] = mapped_column(
        String(150),
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    wallet: Mapped["TokenWallet"] = relationship(
        back_populates="allocations"
    )
