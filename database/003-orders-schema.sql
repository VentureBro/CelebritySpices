CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,

    shopify_order_id VARCHAR(150) NOT NULL UNIQUE,
    shopify_order_name VARCHAR(100),

    financial_status VARCHAR(50),
    fulfillment_status VARCHAR(50),

    customer_name VARCHAR(200),

    operational_status VARCHAR(50) NOT NULL DEFAULT 'new',

    shopify_created_at TIMESTAMPTZ,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_shopify_created_at
ON orders (shopify_created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_operational_status
ON orders (operational_status);


CREATE TABLE IF NOT EXISTS order_items (
    id BIGSERIAL PRIMARY KEY,

    order_id BIGINT NOT NULL
        REFERENCES orders(id)
        ON DELETE CASCADE,

    shopify_line_item_id VARCHAR(150) NOT NULL UNIQUE,

    sku VARCHAR(100),

    product_name VARCHAR(200) NOT NULL,

    quantity INTEGER NOT NULL DEFAULT 0,
    current_quantity INTEGER NOT NULL DEFAULT 0,

    shopify_variant_id VARCHAR(150),

    inventory_item_id BIGINT
        REFERENCES inventory_items(id)
        ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id
ON order_items (order_id);

CREATE INDEX IF NOT EXISTS idx_order_items_sku
ON order_items (sku);

CREATE INDEX IF NOT EXISTS idx_order_items_inventory_item_id
ON order_items (inventory_item_id);
