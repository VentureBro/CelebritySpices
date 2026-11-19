BEGIN;

CREATE TABLE IF NOT EXISTS token_wallets (
    id BIGSERIAL PRIMARY KEY,

    wallet_address VARCHAR(64) NOT NULL UNIQUE,
    token_account_address VARCHAR(64) UNIQUE,

    wallet_type VARCHAR(30) NOT NULL DEFAULT 'influencer',
    display_name VARCHAR(200),

    status VARCHAR(30) NOT NULL DEFAULT 'active',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS token_allocations (
    id BIGSERIAL PRIMARY KEY,

    wallet_id BIGINT NOT NULL
        REFERENCES token_wallets(id)
        ON DELETE RESTRICT,

    amount_base_units BIGINT NOT NULL
        CHECK (amount_base_units > 0),

    token_decimals INTEGER NOT NULL DEFAULT 2,

    allocation_type VARCHAR(40) NOT NULL DEFAULT 'standard',

    blockchain_signature VARCHAR(150) UNIQUE,

    status VARCHAR(30) NOT NULL DEFAULT 'pending',

    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_token_allocations_wallet_id
    ON token_allocations(wallet_id);

CREATE INDEX IF NOT EXISTS idx_token_allocations_status
    ON token_allocations(status);

COMMIT;
