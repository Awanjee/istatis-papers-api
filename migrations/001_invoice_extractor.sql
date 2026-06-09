-- Invoice Extractor tables for iStatis
-- Run in Supabase SQL Editor (Dashboard > SQL Editor > New query)
-- Safe to re-run: uses IF NOT EXISTS throughout
--
-- NOTE: tenant_id is stored as a plain UUID (no FK to tenants table).
-- This is a single-tenant internal tool. The hardcoded tenant UUID is:
--   00000000-0000-0000-0000-000000000001
-- If multi-tenant is needed later, add the FK back and seed a tenants row.

-- -----------------------------------------------------------------------
-- parties
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parties (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID,
    name_roman  TEXT        NOT NULL,
    name_urdu   TEXT,
    party_type  TEXT        DEFAULT 'unknown'
                            CHECK (party_type IN ('supplier', 'buyer', 'unknown')),
    phone       TEXT,
    notes       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- -----------------------------------------------------------------------
-- party_aliases
-- "Feroz", "منشی فیروز", "Munshi Feroz" all resolve to the same party.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS party_aliases (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    party_id    UUID        NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
    alias       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (party_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_party_aliases_lower
    ON party_aliases(lower(alias));

-- -----------------------------------------------------------------------
-- document_extractions
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_extractions (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID,
    image_url            TEXT,
    image_filename       TEXT,
    raw_extraction       JSONB       NOT NULL,
    document_type        TEXT,
    overall_confidence   NUMERIC(3,2),
    has_warnings         BOOLEAN     DEFAULT FALSE,
    low_confidence_fields TEXT[],
    unreadable_sections  TEXT,
    status               TEXT        DEFAULT 'pending_review'
                                     CHECK (status IN (
                                         'pending_review', 'approved',
                                         'rejected', 'error'
                                     )),
    reviewed_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_extractions_tenant_status
    ON document_extractions(tenant_id, status, created_at DESC);

-- -----------------------------------------------------------------------
-- transactions
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID,
    extraction_id    UUID        REFERENCES document_extractions(id),
    party_id         UUID        REFERENCES parties(id),
    transaction_date DATE,
    document_type    TEXT,
    total_amount     NUMERIC(12,2),
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_transactions_tenant_date
    ON transactions(tenant_id, transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_party
    ON transactions(party_id);

-- -----------------------------------------------------------------------
-- transaction_line_items
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transaction_line_items (
    id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID          NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    product_code   TEXT,
    description    TEXT,
    quantity       NUMERIC(12,3),
    unit_price     NUMERIC(12,2),
    amount         NUMERIC(12,2),
    confidence     NUMERIC(3,2),
    notes          TEXT,
    created_at     TIMESTAMPTZ   DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_line_items_transaction
    ON transaction_line_items(transaction_id);
