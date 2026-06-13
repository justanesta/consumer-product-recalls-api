# Constraint Patterns

## Primary Key Strategies

### Surrogate Keys (Recommended Default)

```sql
-- PostgreSQL: IDENTITY column (SQL standard, preferred over SERIAL)
CREATE TABLE orders (
    order_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_date DATE NOT NULL,
    customer_id INT NOT NULL
);

-- MySQL: AUTO_INCREMENT
CREATE TABLE orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    order_date DATE NOT NULL,
    customer_id INT NOT NULL
);

-- SQL Server: IDENTITY
CREATE TABLE orders (
    order_id INT IDENTITY(1,1) PRIMARY KEY,
    order_date DATE NOT NULL,
    customer_id INT NOT NULL
);
```

### Natural Keys (Use Selectively)

```sql
-- Natural key is appropriate when:
-- 1. The value is truly immutable
-- 2. It is already unique and well-defined by a standard
-- 3. Most queries filter by this value

-- Good natural key: ISO country code
CREATE TABLE countries (
    country_code CHAR(2) PRIMARY KEY,   -- ISO 3166-1 alpha-2
    country_name VARCHAR(100) NOT NULL
);

-- Good natural key: currency code
CREATE TABLE currencies (
    currency_code CHAR(3) PRIMARY KEY,   -- ISO 4217
    currency_name VARCHAR(50) NOT NULL,
    symbol        VARCHAR(5)
);

-- BAD natural key: email (it changes)
-- CREATE TABLE users (
--     email VARCHAR(255) PRIMARY KEY,  -- users change emails
--     ...
-- );

-- BETTER: surrogate PK + natural UNIQUE constraint
CREATE TABLE users (
    user_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email     VARCHAR(255) NOT NULL UNIQUE,
    name      VARCHAR(200) NOT NULL
);
```

### Composite Primary Keys

```sql
-- Junction table for many-to-many relationships
CREATE TABLE student_courses (
    student_id  INT NOT NULL REFERENCES students(student_id),
    course_id   INT NOT NULL REFERENCES courses(course_id),
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    grade       VARCHAR(2),
    PRIMARY KEY (student_id, course_id)
);

-- Time-series with natural composite key
CREATE TABLE daily_stock_prices (
    ticker      VARCHAR(10) NOT NULL,
    trade_date  DATE NOT NULL,
    open_price  NUMERIC(12,4) NOT NULL,
    close_price NUMERIC(12,4) NOT NULL,
    high_price  NUMERIC(12,4) NOT NULL,
    low_price   NUMERIC(12,4) NOT NULL,
    volume      BIGINT NOT NULL,
    PRIMARY KEY (ticker, trade_date)
);

-- When composite keys get unwieldy, add a surrogate
CREATE TABLE order_item_attributes (
    attribute_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       INT NOT NULL,
    product_id     INT NOT NULL,
    attribute_name VARCHAR(100) NOT NULL,
    attribute_value TEXT,
    UNIQUE (order_id, product_id, attribute_name),
    FOREIGN KEY (order_id, product_id) REFERENCES order_items(order_id, product_id)
);
```

## Foreign Key Patterns

### Basic Foreign Keys

```sql
-- Inline syntax
CREATE TABLE orders (
    order_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(customer_id),
    order_date  DATE NOT NULL
);

-- Named constraint (preferred for clarity)
CREATE TABLE order_items (
    order_item_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id      INT NOT NULL,
    product_id    INT NOT NULL,
    quantity      INT NOT NULL,

    CONSTRAINT fk_orderitem_order FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    CONSTRAINT fk_orderitem_product FOREIGN KEY (product_id)
        REFERENCES products(product_id)
);
```

### Cascade Behaviors

```sql
-- ON DELETE CASCADE: child rows deleted when parent is deleted
-- Use for: log entries, line items, tags
CREATE TABLE order_items (
    order_item_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id      INT NOT NULL,
    product_id    INT NOT NULL,
    quantity      INT NOT NULL,
    CONSTRAINT fk_orderitem_order FOREIGN KEY (order_id)
        REFERENCES orders(order_id) ON DELETE CASCADE
);
-- Deleting an order automatically deletes all its items

-- ON DELETE RESTRICT (default): prevent parent deletion if children exist
-- Use for: most relationships, prevents accidental data loss
CREATE TABLE orders (
    order_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INT NOT NULL,
    CONSTRAINT fk_order_customer FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id) ON DELETE RESTRICT
);
-- Cannot delete a customer who has orders

-- ON DELETE SET NULL: set FK to NULL when parent is deleted
-- Use for: optional relationships (manager leaves, keep employee)
CREATE TABLE employees (
    employee_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    manager_id  INT,
    CONSTRAINT fk_employee_manager FOREIGN KEY (manager_id)
        REFERENCES employees(employee_id) ON DELETE SET NULL
);
-- Deleting a manager sets their reports' manager_id to NULL

-- ON DELETE SET DEFAULT: set FK to a default value
CREATE TABLE tasks (
    task_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    assigned_to INT DEFAULT 0,
    CONSTRAINT fk_task_assignee FOREIGN KEY (assigned_to)
        REFERENCES users(user_id) ON DELETE SET DEFAULT
);

-- ON UPDATE CASCADE: propagate PK changes to FK columns
-- Useful with natural keys that might change
CREATE TABLE provinces (
    province_code CHAR(2) PRIMARY KEY,
    province_name VARCHAR(100) NOT NULL
);

CREATE TABLE cities (
    city_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    city_name     VARCHAR(100) NOT NULL,
    province_code CHAR(2) NOT NULL,
    CONSTRAINT fk_city_province FOREIGN KEY (province_code)
        REFERENCES provinces(province_code) ON UPDATE CASCADE
);
-- Renaming a province code automatically updates all cities
```

### Cascade Behavior Summary

| Action | `RESTRICT` | `CASCADE` | `SET NULL` | `SET DEFAULT` |
|--------|-----------|-----------|------------|---------------|
| Delete parent | Blocked | Deletes children | Sets FK to NULL | Sets FK to default |
| Update parent PK | Blocked | Updates children FK | Sets FK to NULL | Sets FK to default |
| Safe default? | Yes | Use carefully | Only if FK is nullable | Rarely used |

## UNIQUE Constraints

```sql
-- Single column unique
CREATE TABLE users (
    user_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email    VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(50) NOT NULL UNIQUE
);

-- Multi-column unique (combination must be unique)
CREATE TABLE product_prices (
    price_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id   INT NOT NULL REFERENCES products(product_id),
    region_code  CHAR(2) NOT NULL,
    effective_date DATE NOT NULL,
    price        NUMERIC(10,2) NOT NULL,
    CONSTRAINT uq_product_region_date UNIQUE (product_id, region_code, effective_date)
);

-- Partial unique (PostgreSQL): unique only within a subset
CREATE UNIQUE INDEX uq_active_subscription ON subscriptions(customer_id)
    WHERE status = 'active';
-- Each customer can have only ONE active subscription
-- But multiple cancelled or expired subscriptions are fine
```

## CHECK Constraints

```sql
-- Simple value checks
CREATE TABLE products (
    product_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    price       NUMERIC(10,2) NOT NULL,
    weight_kg   NUMERIC(8,3),
    status      VARCHAR(20) NOT NULL,

    CONSTRAINT chk_price_positive CHECK (price > 0),
    CONSTRAINT chk_weight_positive CHECK (weight_kg IS NULL OR weight_kg > 0),
    CONSTRAINT chk_status_valid CHECK (status IN ('active', 'discontinued', 'draft'))
);

-- Range checks
CREATE TABLE events (
    event_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    start_date  TIMESTAMPTZ NOT NULL,
    end_date    TIMESTAMPTZ NOT NULL,
    capacity    INT,

    CONSTRAINT chk_dates_valid CHECK (end_date > start_date),
    CONSTRAINT chk_capacity_range CHECK (capacity IS NULL OR (capacity >= 1 AND capacity <= 100000))
);

-- Multi-column checks
CREATE TABLE discounts (
    discount_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    discount_type   VARCHAR(20) NOT NULL,
    flat_amount     NUMERIC(10,2),
    percent_amount  NUMERIC(5,2),

    CONSTRAINT chk_discount_type CHECK (discount_type IN ('flat', 'percent')),
    CONSTRAINT chk_discount_value CHECK (
        (discount_type = 'flat' AND flat_amount > 0 AND percent_amount IS NULL)
        OR
        (discount_type = 'percent' AND percent_amount BETWEEN 0.01 AND 100.00 AND flat_amount IS NULL)
    )
);

-- Pattern matching (PostgreSQL)
CREATE TABLE contacts (
    contact_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email      VARCHAR(255) NOT NULL,
    phone      VARCHAR(20),

    CONSTRAINT chk_email_format CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$'),
    CONSTRAINT chk_phone_format CHECK (phone IS NULL OR phone ~ '^\+?[0-9\-\(\) ]{7,20}$')
);
```

## Deferrable Constraints

For transactions that temporarily violate constraints before completing.

```sql
-- PostgreSQL: deferrable foreign key
CREATE TABLE nodes (
    node_id   INT PRIMARY KEY,
    parent_id INT,
    CONSTRAINT fk_node_parent FOREIGN KEY (parent_id)
        REFERENCES nodes(node_id)
        DEFERRABLE INITIALLY DEFERRED
);

-- Insert circular reference in a single transaction
BEGIN;
    INSERT INTO nodes (node_id, parent_id) VALUES (1, 2);  -- parent 2 doesn't exist yet
    INSERT INTO nodes (node_id, parent_id) VALUES (2, 1);  -- now both exist
COMMIT;
-- Constraint is checked at COMMIT, not at each INSERT

-- Deferring mid-transaction
SET CONSTRAINTS fk_node_parent DEFERRED;
-- ... perform operations ...
SET CONSTRAINTS fk_node_parent IMMEDIATE;  -- force check now
```

## Self-Referencing Foreign Keys

```sql
-- Employee hierarchy
CREATE TABLE employees (
    employee_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    manager_id  INT,
    CONSTRAINT fk_employee_manager FOREIGN KEY (manager_id)
        REFERENCES employees(employee_id) ON DELETE SET NULL
);

-- Category tree
CREATE TABLE categories (
    category_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    parent_id     INT,
    depth         INT NOT NULL DEFAULT 0,
    CONSTRAINT fk_category_parent FOREIGN KEY (parent_id)
        REFERENCES categories(category_id) ON DELETE CASCADE,
    CONSTRAINT chk_no_self_ref CHECK (category_id != parent_id)
);
```

## Exclusion Constraints (PostgreSQL)

Prevent overlapping ranges.

```sql
-- Requires btree_gist extension
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Prevent overlapping room bookings
CREATE TABLE room_bookings (
    booking_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id     INT NOT NULL REFERENCES rooms(room_id),
    start_time  TIMESTAMPTZ NOT NULL,
    end_time    TIMESTAMPTZ NOT NULL,
    booked_by   INT NOT NULL REFERENCES users(user_id),

    CONSTRAINT chk_booking_times CHECK (end_time > start_time),
    CONSTRAINT excl_no_overlap EXCLUDE USING gist (
        room_id WITH =,
        tstzrange(start_time, end_time) WITH &&
    )
);
-- Two bookings for the same room with overlapping time ranges are rejected
```

## Constraint Naming Conventions

```sql
-- Consistent naming makes constraints discoverable in error messages
-- Pattern: {type}_{table}_{column(s)}

-- Primary key:   pk_{table}
-- Foreign key:   fk_{table}_{referenced_table} or fk_{table}_{column}
-- Unique:        uq_{table}_{column(s)}
-- Check:         chk_{table}_{description}
-- Exclusion:     excl_{table}_{description}

ALTER TABLE orders
    ADD CONSTRAINT pk_orders PRIMARY KEY (order_id),
    ADD CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    ADD CONSTRAINT uq_orders_reference UNIQUE (order_reference),
    ADD CONSTRAINT chk_orders_amount_positive CHECK (total_amount >= 0);
```
