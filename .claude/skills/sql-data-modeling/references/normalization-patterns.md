# Normalization Patterns

## Unnormalized Data (Starting Point)

```sql
-- Flat denormalized table with repeating groups and mixed concerns
-- This is a common starting point from spreadsheet imports or legacy systems
CREATE TABLE raw_orders (
    order_id        INT,
    order_date      DATE,
    customer_name   VARCHAR(100),
    customer_email  VARCHAR(255),
    customer_city   VARCHAR(100),
    customer_state  VARCHAR(2),
    item1_name      VARCHAR(200),
    item1_price     NUMERIC(10,2),
    item1_qty       INT,
    item2_name      VARCHAR(200),
    item2_price     NUMERIC(10,2),
    item2_qty       INT,
    item3_name      VARCHAR(200),
    item3_price     NUMERIC(10,2),
    item3_qty       INT
);
```

Problems: repeating groups (item1, item2, item3), mixed entities, no referential integrity.

## First Normal Form (1NF)

**Rules**: Atomic values, no repeating groups, unique row identifier.

```sql
-- Step 1: Eliminate repeating groups into separate rows
CREATE TABLE orders_1nf (
    order_id        INT NOT NULL,
    order_date      DATE NOT NULL,
    customer_name   VARCHAR(100) NOT NULL,
    customer_email  VARCHAR(255) NOT NULL,
    customer_city   VARCHAR(100),
    customer_state  VARCHAR(2),
    item_name       VARCHAR(200) NOT NULL,
    item_price      NUMERIC(10,2) NOT NULL,
    item_qty        INT NOT NULL,
    PRIMARY KEY (order_id, item_name)
);

-- Each item is now its own row, no more item1/item2/item3 columns
-- Every column holds a single atomic value
INSERT INTO orders_1nf VALUES
    (1001, '2024-03-15', 'Alice Chen', 'alice@example.com', 'Portland', 'OR', 'Widget A', 29.99, 2),
    (1001, '2024-03-15', 'Alice Chen', 'alice@example.com', 'Portland', 'OR', 'Gadget B', 49.99, 1),
    (1002, '2024-03-16', 'Bob Jones', 'bob@example.com', 'Seattle', 'WA', 'Widget A', 29.99, 5);
```

## Second Normal Form (2NF)

**Rules**: Must be in 1NF + no partial dependencies (every non-key column depends on the entire composite key).

```sql
-- Problem in 1NF: customer_name, customer_email depend only on order_id,
-- not on (order_id, item_name). That is a partial dependency.

-- Step 2: Split into tables where non-key columns depend on the FULL primary key
CREATE TABLE orders_2nf (
    order_id        INT PRIMARY KEY,
    order_date      DATE NOT NULL,
    customer_name   VARCHAR(100) NOT NULL,
    customer_email  VARCHAR(255) NOT NULL,
    customer_city   VARCHAR(100),
    customer_state  VARCHAR(2)
);

CREATE TABLE order_items_2nf (
    order_id    INT NOT NULL REFERENCES orders_2nf(order_id),
    item_name   VARCHAR(200) NOT NULL,
    item_price  NUMERIC(10,2) NOT NULL,
    item_qty    INT NOT NULL,
    PRIMARY KEY (order_id, item_name)
);
```

## Third Normal Form (3NF)

**Rules**: Must be in 2NF + no transitive dependencies (non-key columns depend only on the primary key, not on other non-key columns).

```sql
-- Problem in 2NF: customer_city and customer_state depend on customer_email
-- (or a customer identifier), not directly on order_id. That is transitive.

-- Step 3: Extract entities that depend on something other than the PK
CREATE TABLE customers (
    customer_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    email        VARCHAR(255) NOT NULL UNIQUE,
    city         VARCHAR(100),
    state        VARCHAR(2)
);

CREATE TABLE products (
    product_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL UNIQUE,
    unit_price   NUMERIC(10,2) NOT NULL
);

CREATE TABLE orders (
    order_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  INT NOT NULL REFERENCES customers(customer_id),
    order_date   DATE NOT NULL
);

CREATE TABLE order_items (
    order_item_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id      INT NOT NULL REFERENCES orders(order_id),
    product_id    INT NOT NULL REFERENCES products(product_id),
    quantity      INT NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10,2) NOT NULL,
    UNIQUE (order_id, product_id)
);
-- Note: unit_price is stored on order_items because prices change over time.
-- The price at time of sale differs from the current product catalog price.
```

## Boyce-Codd Normal Form (BCNF)

**Rules**: Must be in 3NF + every determinant is a candidate key.

```sql
-- Example: course scheduling where one teacher teaches one subject,
-- but a subject can be taught by multiple teachers
-- student_id, subject -> teacher  (functional dependency)
-- teacher -> subject              (teacher determines subject, but teacher is not a key)

-- Violates BCNF because teacher determines subject, but teacher is not a candidate key

-- BCNF solution: decompose
CREATE TABLE teacher_subjects (
    teacher_id  INT PRIMARY KEY,
    subject_id  INT NOT NULL REFERENCES subjects(subject_id),
    UNIQUE (teacher_id, subject_id)
);

CREATE TABLE student_enrollments (
    student_id  INT NOT NULL REFERENCES students(student_id),
    teacher_id  INT NOT NULL REFERENCES teacher_subjects(teacher_id),
    PRIMARY KEY (student_id, teacher_id)
);
-- Now every determinant (teacher_id) is a candidate key in its table
```

## When to Stop Normalizing

### Stop at 3NF when:

```sql
-- Typical OLTP application: 3NF is the sweet spot
-- Clean entity separation, referential integrity, manageable joins

-- Example: e-commerce system at 3NF
-- customers -> orders -> order_items -> products -> categories
-- Each entity is self-contained, FK relationships are clear
-- Queries rarely need more than 3-4 joins
```

### Stop at 2NF when:

```sql
-- Logging and event tables where write speed matters
-- Denormalizing customer_name into the events table avoids a join
CREATE TABLE audit_events (
    event_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type     VARCHAR(50) NOT NULL,
    user_id        INT NOT NULL,
    user_name      VARCHAR(100) NOT NULL,  -- denormalized from users table
    entity_type    VARCHAR(50) NOT NULL,
    entity_id      INT NOT NULL,
    event_data     JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- user_name depends on user_id (partial dep), but we accept this
-- because audit logs must not change when a user renames themselves
```

### Denormalize intentionally when:

```sql
-- Data warehouse fact table: fully denormalized for analytics
-- Star schema intentionally breaks 3NF for query performance
CREATE TABLE fact_daily_revenue (
    date_key         INT NOT NULL,
    store_key        INT NOT NULL,
    product_key      INT NOT NULL,
    -- Denormalized attributes for fast filtering without joins
    store_region     VARCHAR(50) NOT NULL,
    product_category VARCHAR(100) NOT NULL,
    -- Measures
    units_sold       INT NOT NULL,
    gross_revenue    NUMERIC(12,2) NOT NULL,
    discount_amount  NUMERIC(12,2) NOT NULL DEFAULT 0,
    net_revenue      NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (date_key, store_key, product_key)
);
```

## Normalization Trade-Offs

| Normal Form | Benefit | Cost | Best For |
|-------------|---------|------|----------|
| **1NF** | Eliminates repeating groups | Minimal overhead | Minimum standard for any database |
| **2NF** | Reduces redundancy with composite keys | Additional tables | Tables with composite primary keys |
| **3NF** | Full entity separation, strong integrity | More joins required | OLTP systems, transactional applications |
| **BCNF** | Eliminates all redundancy from FDs | May lose dependency preservation | Academic or high-integrity systems |
| **Denormalized** | Fewer joins, faster reads | Update anomalies, data redundancy | Data warehouses, read-heavy analytics |

## Common Normalization Mistakes

```sql
-- MISTAKE: Storing derived data that can become stale
CREATE TABLE orders_bad (
    order_id     INT PRIMARY KEY,
    customer_id  INT NOT NULL,
    item_count   INT,          -- can be derived from order_items
    total_amount NUMERIC(10,2) -- can be derived from order_items
);

-- BETTER: Compute at query time or use a materialized view
CREATE MATERIALIZED VIEW order_totals AS
SELECT
    o.order_id,
    COUNT(oi.order_item_id) AS item_count,
    SUM(oi.quantity * oi.unit_price) AS total_amount
FROM orders o
INNER JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id;

-- ACCEPTABLE: Store derived data when query performance is critical
-- BUT add a trigger or scheduled job to keep it in sync
ALTER TABLE orders ADD COLUMN total_amount NUMERIC(12,2);
-- Document that this column is denormalized and maintained by trigger
```

## Multi-Valued Dependencies (4NF Preview)

```sql
-- Problem: employee has independent multi-valued facts
-- An employee can have multiple skills AND multiple certifications
-- These are independent of each other

-- BAD: single table creates spurious combinations
CREATE TABLE employee_skills_certs_bad (
    employee_id      INT NOT NULL,
    skill            VARCHAR(100),
    certification    VARCHAR(100)
);
-- Inserting 3 skills x 2 certs = 6 rows (cartesian explosion)

-- GOOD (4NF): separate independent multi-valued facts
CREATE TABLE employee_skills (
    employee_id INT NOT NULL REFERENCES employees(employee_id),
    skill       VARCHAR(100) NOT NULL,
    PRIMARY KEY (employee_id, skill)
);

CREATE TABLE employee_certifications (
    employee_id    INT NOT NULL REFERENCES employees(employee_id),
    certification  VARCHAR(100) NOT NULL,
    earned_date    DATE NOT NULL,
    PRIMARY KEY (employee_id, certification)
);
```

## Practical Decision Flowchart

1. **Is there a repeating group?** -> Break into separate table (1NF)
2. **Does a non-key column depend on only part of a composite key?** -> Extract to its own table (2NF)
3. **Does a non-key column depend on another non-key column?** -> Extract the transitive chain (3NF)
4. **Is every determinant a candidate key?** -> If not, decompose further (BCNF)
5. **Are there independent multi-valued dependencies?** -> Separate tables (4NF)
6. **Is this an analytics/warehouse workload?** -> Consider denormalizing back strategically
