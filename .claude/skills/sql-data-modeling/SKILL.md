---
name: sql-data-modeling
description: |
  Schema design, normalization, constraints, indexing, and data warehouse modeling patterns.
  Use this skill when designing database schemas, choosing between normalized and denormalized
  structures, implementing star schemas, handling slowly changing dimensions, defining constraints,
  or planning index strategies. Covers normalization through 3NF, denormalization trade-offs,
  star schema design, SCD types, constraint patterns, and indexing fundamentals.
---

# SQL Data Modeling

Essential patterns for designing robust, performant database schemas.

## Core Principles

1. **Model the business domain first** - Tables should reflect real-world entities and relationships
2. **Normalize for integrity, denormalize for performance** - Start normalized, denormalize with evidence
3. **Enforce constraints at the database level** - Never rely solely on application logic for data integrity
4. **Design for query patterns** - Schema should serve the most common read and write workloads
5. **Plan for change** - Use surrogate keys and flexible structures that accommodate evolving requirements

## Normalization Fundamentals

```sql
-- Unnormalized: repeating groups and mixed concerns
-- orders(order_id, customer_name, customer_email, item1, price1, item2, price2)

-- 1NF: Atomic values, no repeating groups
CREATE TABLE orders (
    order_id     INT PRIMARY KEY,
    customer_id  INT NOT NULL,
    order_date   DATE NOT NULL
);

CREATE TABLE order_items (
    order_item_id  INT PRIMARY KEY,
    order_id       INT NOT NULL REFERENCES orders(order_id),
    product_name   VARCHAR(200) NOT NULL,
    unit_price     NUMERIC(10,2) NOT NULL,
    quantity       INT NOT NULL CHECK (quantity > 0)
);

-- 2NF: Remove partial dependencies (every non-key depends on full PK)
-- 3NF: Remove transitive dependencies (non-key columns depend only on the PK)
CREATE TABLE customers (
    customer_id  INT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    email        VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id   INT PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    unit_price   NUMERIC(10,2) NOT NULL
);
```

See [normalization-patterns.md](references/normalization-patterns.md) for:
- Step-by-step 1NF through BCNF walkthrough
- When to stop normalizing
- Normal form trade-offs and decision criteria

## Denormalization Strategies

```sql
-- Precomputed summary table for dashboard queries
CREATE TABLE daily_sales_summary (
    summary_date    DATE NOT NULL,
    product_id      INT NOT NULL REFERENCES products(product_id),
    category_id     INT NOT NULL REFERENCES categories(category_id),
    total_quantity  INT NOT NULL DEFAULT 0,
    total_revenue   NUMERIC(12,2) NOT NULL DEFAULT 0,
    order_count     INT NOT NULL DEFAULT 0,
    PRIMARY KEY (summary_date, product_id)
);

-- Refresh pattern: truncate and reload daily
INSERT INTO daily_sales_summary (summary_date, product_id, category_id, total_quantity, total_revenue, order_count)
SELECT
    o.order_date,
    oi.product_id,
    p.category_id,
    SUM(oi.quantity),
    SUM(oi.quantity * oi.unit_price),
    COUNT(DISTINCT o.order_id)
FROM orders o
INNER JOIN order_items oi ON o.order_id = oi.order_id
INNER JOIN products p ON oi.product_id = p.product_id
WHERE o.order_date = CURRENT_DATE - INTERVAL '1 day'
GROUP BY o.order_date, oi.product_id, p.category_id;
```

See [star-schema-design.md](references/star-schema-design.md) for:
- Fact and dimension table design patterns
- Surrogate keys and conformed dimensions
- When denormalization is appropriate

## Star Schema Design

```sql
-- Fact table: measurable business events
CREATE TABLE fact_sales (
    sale_key        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date_key        INT NOT NULL REFERENCES dim_date(date_key),
    product_key     INT NOT NULL REFERENCES dim_product(product_key),
    customer_key    INT NOT NULL REFERENCES dim_customer(customer_key),
    store_key       INT NOT NULL REFERENCES dim_store(store_key),
    quantity_sold   INT NOT NULL,
    unit_price      NUMERIC(10,2) NOT NULL,
    discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    net_amount      NUMERIC(12,2) NOT NULL
);

-- Dimension table: descriptive context
CREATE TABLE dim_product (
    product_key     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id      VARCHAR(20) NOT NULL,
    product_name    VARCHAR(200) NOT NULL,
    category        VARCHAR(100) NOT NULL,
    subcategory     VARCHAR(100),
    brand           VARCHAR(100),
    effective_date  DATE NOT NULL,
    expiration_date DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);
```

See [star-schema-design.md](references/star-schema-design.md) for:
- Fact table types (transaction, periodic snapshot, accumulating snapshot)
- Dimension table patterns and junk dimensions
- Conformed dimensions across multiple fact tables

## Slowly Changing Dimensions

```sql
-- SCD Type 2: Track full history with versioned rows
-- Close the current record
UPDATE dim_customer
SET expiration_date = CURRENT_DATE - INTERVAL '1 day',
    is_current = FALSE
WHERE customer_id = 'C-1001'
  AND is_current = TRUE;

-- Insert updated record
INSERT INTO dim_customer (customer_id, name, email, city, state, effective_date, expiration_date, is_current)
VALUES ('C-1001', 'Jane Smith', 'jane.new@example.com', 'Denver', 'CO', CURRENT_DATE, '9999-12-31', TRUE);
```

See [slowly-changing-dimensions.md](references/slowly-changing-dimensions.md) for:
- SCD Types 1, 2, 3, 4, and 6 with full implementation patterns
- Choosing the right SCD type for your use case
- Merge/upsert patterns for SCD maintenance

## Constraint Design

```sql
-- Comprehensive constraint example
CREATE TABLE employees (
    employee_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         VARCHAR(255) NOT NULL,
    department_id INT NOT NULL,
    manager_id    INT,
    hire_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    salary        NUMERIC(10,2) NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'active',

    CONSTRAINT uq_employee_email UNIQUE (email),
    CONSTRAINT fk_employee_dept FOREIGN KEY (department_id)
        REFERENCES departments(department_id) ON DELETE RESTRICT,
    CONSTRAINT fk_employee_manager FOREIGN KEY (manager_id)
        REFERENCES employees(employee_id) ON DELETE SET NULL,
    CONSTRAINT chk_salary_positive CHECK (salary > 0),
    CONSTRAINT chk_status_valid CHECK (status IN ('active', 'inactive', 'terminated'))
);
```

See [constraint-patterns.md](references/constraint-patterns.md) for:
- Primary key strategies (natural vs surrogate)
- Foreign key cascade behaviors
- Composite keys and multi-column constraints
- Deferrable constraints for complex transactions

## Indexing Strategy Overview

```sql
-- Primary lookup index
CREATE INDEX idx_orders_customer_id ON orders(customer_id);

-- Composite index for common query pattern
CREATE INDEX idx_orders_date_status ON orders(order_date, status);

-- Covering index to avoid table lookups
CREATE INDEX idx_orders_covering ON orders(customer_id, order_date)
    INCLUDE (total_amount, status);

-- Partial index for active records only
CREATE INDEX idx_active_customers ON customers(email)
    WHERE status = 'active';
```

See [index-design-patterns.md](references/index-design-patterns.md) for:
- B-tree, GIN, and GiST index types
- Covering indexes and index-only scans
- Partial indexes and column order strategy
- When to avoid indexing

## Naming Conventions

See [naming-conventions.md](references/naming-conventions.md) for:
- Table, column, constraint, and index naming standards
- Reserved word avoidance strategies
- Consistent pluralization and casing rules

## Schema Migration Patterns

See [schema-migration-patterns.md](references/schema-migration-patterns.md) for:
- Safe ALTER TABLE operations
- Zero-downtime migration strategies
- Backward-compatible schema changes

## Cross-Database Compatibility

| Feature | PostgreSQL | MySQL | SQL Server |
|---------|-----------|-------|------------|
| Auto-increment PK | `GENERATED ALWAYS AS IDENTITY` | `AUTO_INCREMENT` | `IDENTITY(1,1)` |
| Boolean type | `BOOLEAN` | `TINYINT(1)` / `BOOLEAN` | `BIT` |
| UUID type | `UUID` | `CHAR(36)` / `BINARY(16)` | `UNIQUEIDENTIFIER` |
| JSON column | `JSONB` | `JSON` | `NVARCHAR(MAX)` with `ISJSON` |
| Check constraints | Fully enforced | Enforced (8.0.16+) | Fully enforced |
| Partial indexes | `WHERE` clause on index | Not supported | `WHERE` clause (filtered index) |
| Generated columns | `GENERATED ALWAYS AS (expr) STORED` | `GENERATED ALWAYS AS (expr) STORED/VIRTUAL` | `AS (expr) PERSISTED` |
| Schema namespaces | Schemas (`public.orders`) | Databases (`mydb.orders`) | Schemas (`dbo.orders`) |

## Anti-Patterns to Avoid

| Avoid | Use Instead | Why |
|-------|-------------|-----|
| EAV (Entity-Attribute-Value) tables for structured data | Proper normalized tables or JSONB columns | Impossible to enforce constraints, terrible query performance |
| Single large table with many NULLable columns | Separate related entities into their own tables | Wastes storage, unclear data model, weak integrity |
| Storing comma-separated values in a column | Junction/bridge table for many-to-many relationships | Cannot enforce FK constraints, difficult to query and index |
| Using `VARCHAR` for everything | Appropriate types (`INT`, `DATE`, `NUMERIC`, `BOOLEAN`) | Loses type safety, wastes storage, prevents range operations |
| Missing foreign key constraints | Always declare FK relationships | Orphaned rows, silent data corruption over time |
| Natural keys as primary keys | Surrogate keys with natural key as UNIQUE constraint | Natural keys change, cause cascading updates, complicate joins |
| One huge table for all events | Partitioned tables or separate tables by event type | Query performance degrades, maintenance becomes impossible |

## Performance Considerations

- Start with 3NF for transactional systems; denormalize only when query performance requires it
- Use surrogate integer keys for joins -- they are smaller and faster than string-based keys
- Partition large fact tables by date range for efficient pruning
- Place foreign keys on the "many" side of one-to-many relationships and index them
- Use covering indexes for high-frequency read queries to enable index-only scans
- Prefer `BIGINT` identity columns over `UUID` for clustered indexes to reduce page splits

source: Kimball Group data warehouse toolkit, PostgreSQL docs, MySQL docs, SQL Server docs, database normalization theory
