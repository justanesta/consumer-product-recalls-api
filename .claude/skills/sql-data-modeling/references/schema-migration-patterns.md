# Schema Migration Patterns

## Safe ALTER TABLE Operations

### Adding Columns

```sql
-- SAFE: Adding a nullable column (no table rewrite, instant in most databases)
ALTER TABLE orders ADD COLUMN tracking_number VARCHAR(100);

-- SAFE: Adding a column with a default (PostgreSQL 11+, instant; older versions rewrite)
ALTER TABLE orders ADD COLUMN priority VARCHAR(20) NOT NULL DEFAULT 'normal';

-- CAUTION: Adding NOT NULL without a default on an existing table
-- This FAILS if the table has existing rows (PostgreSQL, SQL Server)
-- ALTER TABLE orders ADD COLUMN region VARCHAR(50) NOT NULL;  -- ERROR

-- SAFE approach for NOT NULL columns on existing tables:
-- Step 1: Add nullable column
ALTER TABLE orders ADD COLUMN region VARCHAR(50);
-- Step 2: Backfill data
UPDATE orders SET region = 'US-EAST' WHERE region IS NULL;
-- Step 3: Add NOT NULL constraint
ALTER TABLE orders ALTER COLUMN region SET NOT NULL;
```

### Dropping Columns

```sql
-- SAFE in PostgreSQL: column is marked as dropped (no rewrite)
ALTER TABLE orders DROP COLUMN IF EXISTS legacy_notes;

-- MySQL: requires table rebuild (can be slow on large tables)
ALTER TABLE orders DROP COLUMN legacy_notes;

-- SAFE approach: deprecate before dropping
-- Step 1: Stop writing to the column in application code
-- Step 2: Deploy and verify no reads from the column
-- Step 3: Drop the column in a subsequent migration
ALTER TABLE orders DROP COLUMN legacy_notes;
```

### Renaming Columns

```sql
-- PostgreSQL: metadata-only change (instant)
ALTER TABLE orders RENAME COLUMN ship_date TO shipped_at;

-- MySQL (5.7+): instant with ALGORITHM=INSTANT where supported
ALTER TABLE orders CHANGE ship_date shipped_at DATETIME;

-- SQL Server:
EXEC sp_rename 'orders.ship_date', 'shipped_at', 'COLUMN';

-- WARNING: Renaming breaks any application code, views, or queries
-- referencing the old column name. Use the expand-and-contract pattern instead.
```

## Zero-Downtime Migration (Expand and Contract)

The safest approach for production systems. Changes are split into backward-compatible steps.

### Renaming a Column (Zero-Downtime)

```sql
-- Phase 1: EXPAND - Add new column alongside old
ALTER TABLE customers ADD COLUMN full_name VARCHAR(200);

-- Phase 2: MIGRATE - Copy data and keep in sync
UPDATE customers SET full_name = customer_name WHERE full_name IS NULL;

-- Add a trigger to keep both columns in sync during transition
CREATE OR REPLACE FUNCTION sync_customer_name() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.customer_name IS DISTINCT FROM OLD.customer_name THEN
        NEW.full_name := NEW.customer_name;
    END IF;
    IF NEW.full_name IS DISTINCT FROM OLD.full_name THEN
        NEW.customer_name := NEW.full_name;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_customer_name
    BEFORE INSERT OR UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION sync_customer_name();

-- Phase 3: TRANSITION - Update application to read/write new column
-- Deploy code that uses full_name instead of customer_name

-- Phase 4: CONTRACT - Remove old column and trigger
DROP TRIGGER trg_sync_customer_name ON customers;
DROP FUNCTION sync_customer_name();
ALTER TABLE customers DROP COLUMN customer_name;
```

### Changing Column Type (Zero-Downtime)

```sql
-- Changing a column from VARCHAR(50) to VARCHAR(200)
-- PostgreSQL: Some type changes are metadata-only (e.g., extending VARCHAR length)
ALTER TABLE products ALTER COLUMN description TYPE VARCHAR(200);
-- This is safe and fast in PostgreSQL (no rewrite for extending varchar)

-- Changing from VARCHAR to INT (requires data conversion)
-- Phase 1: Add new column
ALTER TABLE orders ADD COLUMN priority_level INT;

-- Phase 2: Backfill with conversion
UPDATE orders
SET priority_level = CASE priority_text
    WHEN 'low' THEN 1
    WHEN 'medium' THEN 2
    WHEN 'high' THEN 3
    WHEN 'critical' THEN 4
    ELSE 0
END;

-- Phase 3: Add sync trigger for transition period
CREATE OR REPLACE FUNCTION sync_priority() RETURNS TRIGGER AS $$
BEGIN
    NEW.priority_level := CASE NEW.priority_text
        WHEN 'low' THEN 1 WHEN 'medium' THEN 2
        WHEN 'high' THEN 3 WHEN 'critical' THEN 4 ELSE 0
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_priority
    BEFORE INSERT OR UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION sync_priority();

-- Phase 4: Migrate application code
-- Phase 5: Drop old column and trigger
DROP TRIGGER trg_sync_priority ON orders;
ALTER TABLE orders DROP COLUMN priority_text;
ALTER TABLE orders ALTER COLUMN priority_level SET NOT NULL;
ALTER TABLE orders RENAME COLUMN priority_level TO priority;
```

### Splitting a Table (Zero-Downtime)

```sql
-- Extracting address columns from customers into a separate table

-- Phase 1: Create new table
CREATE TABLE customer_addresses (
    address_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  INT NOT NULL REFERENCES customers(customer_id),
    street       VARCHAR(200),
    city         VARCHAR(100),
    state        VARCHAR(2),
    postal_code  VARCHAR(20),
    country      VARCHAR(100),
    is_primary   BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (customer_id, is_primary) -- only one primary address per customer
);

-- Phase 2: Migrate existing data
INSERT INTO customer_addresses (customer_id, street, city, state, postal_code, country)
SELECT customer_id, street, city, state, postal_code, country
FROM customers
WHERE street IS NOT NULL;

-- Phase 3: Add trigger to sync writes during transition
CREATE OR REPLACE FUNCTION sync_customer_address() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO customer_addresses (customer_id, street, city, state, postal_code, country)
    VALUES (NEW.customer_id, NEW.street, NEW.city, NEW.state, NEW.postal_code, NEW.country)
    ON CONFLICT (customer_id, is_primary)
    DO UPDATE SET
        street = EXCLUDED.street,
        city = EXCLUDED.city,
        state = EXCLUDED.state,
        postal_code = EXCLUDED.postal_code,
        country = EXCLUDED.country;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_address
    AFTER INSERT OR UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION sync_customer_address();

-- Phase 4: Update application to read/write from customer_addresses
-- Phase 5: Drop sync trigger and old columns
DROP TRIGGER trg_sync_address ON customers;
DROP FUNCTION sync_customer_address();
ALTER TABLE customers DROP COLUMN street;
ALTER TABLE customers DROP COLUMN city;
ALTER TABLE customers DROP COLUMN state;
ALTER TABLE customers DROP COLUMN postal_code;
ALTER TABLE customers DROP COLUMN country;
```

## Adding Constraints Safely

```sql
-- Adding a NOT NULL constraint on a populated column
-- Step 1: Verify no nulls exist
SELECT COUNT(*) FROM orders WHERE region IS NULL;
-- Step 2: Backfill if needed
UPDATE orders SET region = 'UNKNOWN' WHERE region IS NULL;
-- Step 3: Add constraint
ALTER TABLE orders ALTER COLUMN region SET NOT NULL;

-- Adding a foreign key without blocking writes (PostgreSQL)
-- NOT VALID skips checking existing rows (instant)
ALTER TABLE orders
    ADD CONSTRAINT fk_orders_customers
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    NOT VALID;

-- Then validate in a separate step (scans table but doesn't hold exclusive lock)
ALTER TABLE orders VALIDATE CONSTRAINT fk_orders_customers;

-- Adding a CHECK constraint without blocking (PostgreSQL)
ALTER TABLE products
    ADD CONSTRAINT chk_price_positive CHECK (price > 0) NOT VALID;
ALTER TABLE products VALIDATE CONSTRAINT chk_price_positive;
```

## Creating Indexes Without Downtime

```sql
-- PostgreSQL: CONCURRENTLY avoids locking the table for writes
CREATE INDEX CONCURRENTLY idx_orders_customer_date ON orders(customer_id, order_date);
-- Takes longer but does not block INSERT/UPDATE/DELETE
-- Cannot be run inside a transaction block

-- MySQL: Online DDL (InnoDB)
ALTER TABLE orders ADD INDEX idx_orders_customer_date (customer_id, order_date),
    ALGORITHM=INPLACE, LOCK=NONE;

-- SQL Server: ONLINE option
CREATE INDEX idx_orders_customer_date ON orders(customer_id, order_date) WITH (ONLINE = ON);

-- Replacing an index (PostgreSQL)
-- Step 1: Create new index concurrently
CREATE INDEX CONCURRENTLY idx_orders_customer_date_v2 ON orders(customer_id, order_date, status);
-- Step 2: Drop old index concurrently
DROP INDEX CONCURRENTLY idx_orders_customer_date;
-- Step 3: Rename (optional)
ALTER INDEX idx_orders_customer_date_v2 RENAME TO idx_orders_customer_date;
```

## Backward-Compatible Schema Changes

### Safe Changes (No Application Coordination Needed)

```sql
-- These changes are backward-compatible with old application code:
ALTER TABLE orders ADD COLUMN notes TEXT;                    -- new nullable column
ALTER TABLE orders ADD COLUMN priority INT DEFAULT 0;       -- new column with default
ALTER TABLE orders ALTER COLUMN description TYPE VARCHAR(500); -- extend varchar (PostgreSQL)
CREATE INDEX CONCURRENTLY idx_new ON orders(new_column);    -- new index
```

### Unsafe Changes (Require Coordinated Deployment)

```sql
-- These break old application code and need expand-and-contract:
ALTER TABLE orders DROP COLUMN old_column;          -- old code still references it
ALTER TABLE orders RENAME COLUMN old_name TO new_name; -- old code uses old name
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;    -- old code might insert NULLs
ALTER TABLE orders ALTER COLUMN amount TYPE INT;        -- type change may lose precision
DROP TABLE deprecated_table;                            -- old code might still query it
```

## Batch Data Backfill Pattern

For large tables, update in batches to avoid long-running transactions.

```sql
-- Backfill a new column in batches of 10,000 rows
DO $$
DECLARE
    batch_size INT := 10000;
    rows_updated INT;
BEGIN
    LOOP
        UPDATE orders
        SET region = COALESCE(
            (SELECT r.region_name
             FROM store_regions r
             WHERE r.store_id = orders.store_id),
            'UNKNOWN'
        )
        WHERE order_id IN (
            SELECT order_id FROM orders
            WHERE region IS NULL
            LIMIT batch_size
        );

        GET DIAGNOSTICS rows_updated = ROW_COUNT;
        RAISE NOTICE 'Updated % rows', rows_updated;

        IF rows_updated = 0 THEN
            EXIT;
        END IF;

        -- Small pause to reduce load
        PERFORM pg_sleep(0.1);
    END LOOP;
END $$;
```

## Migration Tooling Patterns

```sql
-- Versioned migration files (used by tools like Flyway, Liquibase, Alembic, knex)
-- Each migration has an up and down (rollback) operation

-- V001__create_customers_table.sql
CREATE TABLE customers (
    customer_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- V002__add_customer_phone.sql
ALTER TABLE customers ADD COLUMN phone VARCHAR(20);

-- V003__add_customer_status.sql
ALTER TABLE customers ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE customers ADD CONSTRAINT chk_customer_status
    CHECK (status IN ('active', 'inactive', 'suspended'));

-- Rollback for V003:
-- ALTER TABLE customers DROP CONSTRAINT chk_customer_status;
-- ALTER TABLE customers DROP COLUMN status;
```

## Migration Safety Checklist

| Check | Description |
|-------|-------------|
| Backward compatible? | Can old code still work after migration runs? |
| Reversible? | Is there a rollback script? |
| Large table? | Use batched updates, CONCURRENTLY for indexes |
| Adding NOT NULL? | Backfill first, then add constraint |
| Adding FK? | Use NOT VALID + VALIDATE for zero-downtime |
| Dropping column? | Ensure no code reads or writes it |
| Renaming? | Use expand-and-contract pattern |
| Tested? | Run against a copy of production data first |
