BEGIN;

CREATE TABLE IF NOT EXISTS warehouses (
    id BIGSERIAL PRIMARY KEY,
    warehouse_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    address_line_1 VARCHAR(200),
    city VARCHAR(100),
    province VARCHAR(100),
    country_code CHAR(2) NOT NULL DEFAULT 'CA',

    -- Shopify Location GID or legacy numeric identifier.
    shopify_location_id VARCHAR(150) UNIQUE,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id BIGSERIAL PRIMARY KEY,

    sku VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,

    barcode VARCHAR(100),
    unit_of_measure VARCHAR(30) NOT NULL DEFAULT 'each',

    -- Shopify identifiers are stored as text because GraphQL uses GIDs.
    shopify_product_id VARCHAR(150),
    shopify_variant_id VARCHAR(150) UNIQUE,
    shopify_inventory_item_id VARCHAR(150) UNIQUE,

    tracks_inventory BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_shopify_sync_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS inventory_levels (
    id BIGSERIAL PRIMARY KEY,

    inventory_item_id BIGINT NOT NULL
        REFERENCES inventory_items(id)
        ON DELETE RESTRICT,

    warehouse_id BIGINT NOT NULL
        REFERENCES warehouses(id)
        ON DELETE RESTRICT,

    on_hand_quantity INTEGER NOT NULL DEFAULT 0,
    committed_quantity INTEGER NOT NULL DEFAULT 0,
    incoming_quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,

    reorder_point INTEGER NOT NULL DEFAULT 0,
    reorder_quantity INTEGER NOT NULL DEFAULT 0,

    shopify_available_quantity INTEGER,
    last_shopify_sync_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT inventory_levels_item_warehouse_unique
        UNIQUE (inventory_item_id, warehouse_id),

    CONSTRAINT inventory_levels_nonnegative_check CHECK (
        on_hand_quantity >= 0
        AND committed_quantity >= 0
        AND incoming_quantity >= 0
        AND reserved_quantity >= 0
        AND reorder_point >= 0
        AND reorder_quantity >= 0
    )
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id BIGSERIAL PRIMARY KEY,

    inventory_item_id BIGINT NOT NULL
        REFERENCES inventory_items(id)
        ON DELETE RESTRICT,

    warehouse_id BIGINT NOT NULL
        REFERENCES warehouses(id)
        ON DELETE RESTRICT,

    movement_type VARCHAR(40) NOT NULL,
    quantity_change INTEGER NOT NULL,

    quantity_before INTEGER NOT NULL,
    quantity_after INTEGER NOT NULL,

    reference_type VARCHAR(50),
    reference_id VARCHAR(150),
    notes TEXT,

    source_system VARCHAR(30) NOT NULL DEFAULT 'operations-platform',

    -- Added later when employee accounts and Solana transactions exist.
    employee_id BIGINT,
    blockchain_signature VARCHAR(150),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT inventory_movement_type_check CHECK (
        movement_type IN (
            'initial',
            'receiving',
            'sale',
            'return',
            'adjustment',
            'transfer_in',
            'transfer_out',
            'damage',
            'correction',
            'shopify_sync'
        )
    )
);

CREATE TABLE IF NOT EXISTS shopify_sync_events (
    id BIGSERIAL PRIMARY KEY,

    webhook_id VARCHAR(150) UNIQUE,
    topic VARCHAR(100) NOT NULL,

    shopify_shop_domain VARCHAR(255),
    resource_id VARCHAR(150),

    direction VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',

    payload JSONB,
    error_message TEXT,

    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,

    CONSTRAINT shopify_sync_direction_check CHECK (
        direction IN ('shopify_to_local', 'local_to_shopify')
    ),

    CONSTRAINT shopify_sync_status_check CHECK (
        status IN ('pending', 'processing', 'completed', 'failed', 'ignored')
    )
);

CREATE INDEX IF NOT EXISTS idx_inventory_items_shopify_product
    ON inventory_items (shopify_product_id);

CREATE INDEX IF NOT EXISTS idx_inventory_items_shopify_inventory_item
    ON inventory_items (shopify_inventory_item_id);

CREATE INDEX IF NOT EXISTS idx_inventory_levels_item
    ON inventory_levels (inventory_item_id);

CREATE INDEX IF NOT EXISTS idx_inventory_levels_warehouse
    ON inventory_levels (warehouse_id);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_item_created
    ON inventory_movements (inventory_item_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_shopify_sync_status
    ON shopify_sync_events (status, received_at);

INSERT INTO warehouses (
    warehouse_code,
    name,
    city,
    province,
    country_code
)
VALUES (
    'MAIN',
    'Primary Operations Warehouse',
    'Richmond',
    'British Columbia',
    'CA'
)
ON CONFLICT (warehouse_code) DO NOTHING;

COMMIT;
