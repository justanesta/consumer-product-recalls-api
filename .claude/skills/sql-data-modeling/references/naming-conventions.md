# Naming Conventions

## General Rules

1. Use `snake_case` for all identifiers (tables, columns, indexes, constraints)
2. Use lowercase exclusively -- avoids quoting issues across databases
3. Be descriptive but concise -- prefer `order_date` over `od` or `the_date_of_the_order`
4. Use consistent singular or plural for tables (pick one and stick with it)
5. Never use SQL reserved words as identifiers

## Table Naming

```sql
-- Singular noun (recommended by many style guides)
CREATE TABLE customer (...);
CREATE TABLE order (...);        -- PROBLEM: 'order' is a reserved word
CREATE TABLE product (...);

-- Plural noun (common alternative, avoids some reserved word conflicts)
CREATE TABLE customers (...);
CREATE TABLE orders (...);       -- 'orders' is not reserved
CREATE TABLE products (...);

-- Pick ONE convention and use it consistently across the entire database
```

### Table Name Patterns

```sql
-- Entity tables: noun describing the business object
CREATE TABLE customers (...);
CREATE TABLE products (...);
CREATE TABLE invoices (...);

-- Junction/bridge tables: combine both entity names
CREATE TABLE student_courses (...);       -- students <-> courses
CREATE TABLE order_items (...);           -- orders <-> items/products
CREATE TABLE user_roles (...);            -- users <-> roles

-- History/audit tables: entity + suffix
CREATE TABLE customers_history (...);
CREATE TABLE products_audit (...);

-- Staging/temporary tables: prefix with context
CREATE TABLE stg_customer_import (...);   -- staging
CREATE TABLE tmp_dedup_results (...);     -- temporary processing

-- Data warehouse tables: prefix with table type
CREATE TABLE fact_sales (...);
CREATE TABLE dim_product (...);
CREATE TABLE dim_date (...);
```

## Column Naming

```sql
-- Primary key: table_name_id (singular) or just id
CREATE TABLE customers (
    customer_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- or simply: id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ...
);

-- Foreign key: referenced_table_id (matches PK name in referenced table)
CREATE TABLE orders (
    order_id      INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id   INT NOT NULL REFERENCES customers(customer_id),
    -- customer_id matches the PK name in the customers table
    ...
);

-- Boolean columns: is_, has_, can_ prefix
CREATE TABLE users (
    user_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    has_verified_email BOOLEAN NOT NULL DEFAULT FALSE,
    can_login     BOOLEAN NOT NULL DEFAULT TRUE
);

-- Date/time columns: suffix with _at or _date or _on
CREATE TABLE orders (
    order_id      INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    order_date    DATE NOT NULL,
    shipped_on    DATE,
    delivered_at  TIMESTAMPTZ
);

-- Amount/count columns: suffix with _amount, _count, _total, _qty
CREATE TABLE order_items (
    order_item_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_price     NUMERIC(10,2) NOT NULL,
    quantity       INT NOT NULL,
    discount_amount NUMERIC(10,2) DEFAULT 0,
    line_total     NUMERIC(12,2) NOT NULL
);

-- Status columns: use descriptive name
CREATE TABLE orders (
    order_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status         VARCHAR(20) NOT NULL DEFAULT 'pending',
    payment_status VARCHAR(20) NOT NULL DEFAULT 'unpaid',
    fulfillment_status VARCHAR(20) NOT NULL DEFAULT 'unfulfilled'
);
```

## Constraint Naming

```sql
-- Primary key: pk_{table}
ALTER TABLE orders ADD CONSTRAINT pk_orders PRIMARY KEY (order_id);

-- Foreign key: fk_{child_table}_{parent_table} or fk_{child_table}_{column}
ALTER TABLE orders ADD CONSTRAINT fk_orders_customers
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id);

ALTER TABLE order_items ADD CONSTRAINT fk_order_items_orders
    FOREIGN KEY (order_id) REFERENCES orders(order_id);

-- Unique: uq_{table}_{column(s)}
ALTER TABLE users ADD CONSTRAINT uq_users_email UNIQUE (email);
ALTER TABLE product_prices ADD CONSTRAINT uq_product_prices_product_region
    UNIQUE (product_id, region_code);

-- Check: chk_{table}_{description}
ALTER TABLE products ADD CONSTRAINT chk_products_price_positive CHECK (price > 0);
ALTER TABLE events ADD CONSTRAINT chk_events_dates_valid CHECK (end_date > start_date);

-- Default: df_{table}_{column}
ALTER TABLE orders ALTER COLUMN status SET DEFAULT 'pending';
-- Named defaults (SQL Server): CONSTRAINT df_orders_status DEFAULT 'pending' FOR status
```

## Index Naming

```sql
-- Pattern: idx_{table}_{column(s)}
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_date_status ON orders(order_date, status);

-- Unique index: uidx_{table}_{column(s)}
CREATE UNIQUE INDEX uidx_users_email ON users(email);

-- Partial index: idx_{table}_{column(s)}_{filter_description}
CREATE INDEX idx_orders_customer_active ON orders(customer_id) WHERE status = 'active';

-- Covering index: idx_{table}_{column(s)}_covering
CREATE INDEX idx_orders_customer_date_covering ON orders(customer_id, order_date)
    INCLUDE (total_amount, status);

-- Expression index: idx_{table}_{expression_description}
CREATE INDEX idx_users_email_lower ON users(LOWER(email));

-- GIN index: gin_{table}_{column}
CREATE INDEX gin_products_attributes ON products USING gin(attributes);
```

## Reserved Words to Avoid

These commonly cause issues as identifiers across databases:

```sql
-- Common reserved words that people try to use as identifiers:
-- order, user, group, table, column, index, key, type, name, value,
-- date, time, timestamp, status, level, position, result, role,
-- language, action, comment, condition, data, domain, end, function,
-- match, option, output, primary, range, read, references, row,
-- schema, scope, select, session, set, size, start, state,
-- system, work, zone

-- BAD: using reserved words
CREATE TABLE order (
    id INT PRIMARY KEY,
    date DATE,
    user INT,
    type VARCHAR(20),
    status VARCHAR(20)
);
-- Must be quoted: "order", "date", "user", "type"
-- Quoting makes every query more painful

-- GOOD: descriptive alternatives
CREATE TABLE orders (
    order_id     INT PRIMARY KEY,
    order_date   DATE,
    customer_id  INT,
    order_type   VARCHAR(20),
    order_status VARCHAR(20)
);
-- No quoting needed, more descriptive, self-documenting
```

## Schema and Database Naming

```sql
-- PostgreSQL schemas
CREATE SCHEMA staging;     -- raw imported data
CREATE SCHEMA analytics;   -- transformed data for reporting
CREATE SCHEMA archive;     -- historical data

-- Use schema-qualified names in queries
SELECT * FROM staging.raw_customers;
SELECT * FROM analytics.customer_segments;

-- Data warehouse layer naming (dbt convention)
-- raw / staging:   raw source data
-- intermediate:    cleaned, joined intermediate models
-- marts:           business-domain-specific final tables

-- Example dbt-style schema organization
CREATE SCHEMA raw;           -- raw.stripe_payments, raw.shopify_orders
CREATE SCHEMA staging;       -- staging.stg_stripe_payments
CREATE SCHEMA intermediate;  -- intermediate.int_payments_pivoted
CREATE SCHEMA marts;         -- marts.fct_orders, marts.dim_customers
```

## Naming Checklist

| Element | Convention | Example |
|---------|-----------|---------|
| Table | `snake_case`, noun | `order_items` |
| Column | `snake_case`, descriptive | `customer_id`, `is_active` |
| Primary key | `{table_singular}_id` or `id` | `customer_id` |
| Foreign key column | Match parent PK name | `customer_id` |
| PK constraint | `pk_{table}` | `pk_customers` |
| FK constraint | `fk_{child}_{parent}` | `fk_orders_customers` |
| Unique constraint | `uq_{table}_{cols}` | `uq_users_email` |
| Check constraint | `chk_{table}_{desc}` | `chk_products_price_positive` |
| Index | `idx_{table}_{cols}` | `idx_orders_customer_date` |
| Unique index | `uidx_{table}_{cols}` | `uidx_users_username` |
| Staging table | `stg_{source}_{entity}` | `stg_stripe_payments` |
| Fact table | `fact_{process}` | `fact_sales` |
| Dimension table | `dim_{entity}` | `dim_product` |
| Boolean column | `is_`, `has_`, `can_` prefix | `is_active`, `has_discount` |
| Timestamp column | `_at` suffix | `created_at`, `updated_at` |
| Date column | `_date` or `_on` suffix | `order_date`, `shipped_on` |

## Common Mistakes

```sql
-- MISTAKE: Inconsistent casing
CREATE TABLE CustomerOrders (...);   -- PascalCase
CREATE TABLE order_items (...);      -- snake_case
-- Pick ONE style for the whole database

-- MISTAKE: Abbreviations that are unclear
CREATE TABLE cust_ord_itm (...);     -- What is this?
CREATE TABLE customer_order_items (...);  -- Clear

-- MISTAKE: Prefixing every column with table name
CREATE TABLE customers (
    customers_id INT,
    customers_name VARCHAR(100),
    customers_email VARCHAR(255)
);
-- Redundant. Use: customer_id, name, email
-- Exception: when column name alone is ambiguous (e.g., customer_id as FK)

-- MISTAKE: Using generic names
CREATE TABLE data (...);
CREATE TABLE info (...);
CREATE TABLE records (...);
-- These tell you nothing about the business domain
```
