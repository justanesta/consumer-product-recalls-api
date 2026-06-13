# Slowly Changing Dimensions

## Overview

Slowly Changing Dimensions (SCDs) describe how dimension attributes change over time and how the data warehouse should respond. The choice of SCD type depends on whether historical tracking is needed and how much complexity is acceptable.

## SCD Type 0: Retain Original

The attribute value never changes after initial load. Used for true immutable facts.

```sql
-- Date of birth, original registration date, SSN
CREATE TABLE dim_customer_type0 (
    customer_key    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id     VARCHAR(20) NOT NULL UNIQUE,
    name            VARCHAR(200) NOT NULL,
    date_of_birth   DATE NOT NULL,          -- never updated
    registration_date DATE NOT NULL,         -- never updated
    original_segment VARCHAR(50) NOT NULL    -- segment at time of first enrollment
);

-- On update: only update non-Type-0 columns, leave immutable columns alone
UPDATE dim_customer_type0
SET name = 'Jane Smith-Doe'
WHERE customer_id = 'C-1001';
-- date_of_birth, registration_date, original_segment remain unchanged
```

## SCD Type 1: Overwrite

Replace the old value with the new value. No history is preserved.

```sql
CREATE TABLE dim_customer_type1 (
    customer_key    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id     VARCHAR(20) NOT NULL UNIQUE,
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    city            VARCHAR(100),
    state           VARCHAR(2),
    segment         VARCHAR(50)
);

-- Customer moves from Portland, OR to Denver, CO
UPDATE dim_customer_type1
SET city = 'Denver',
    state = 'CO'
WHERE customer_id = 'C-1001';

-- Previous values (Portland, OR) are lost
-- All historical fact rows now associate with the new address
-- Simple, but you can never analyze "sales when customer was in Portland"
```

**When to use Type 1**:
- Correcting data entry errors
- Attributes where history has no analytical value (e.g., fixing a typo in a name)
- When storage and complexity must be minimized

## SCD Type 2: Add New Row (Full History)

Insert a new row for each change, preserving the complete history.

```sql
CREATE TABLE dim_customer_type2 (
    customer_key      INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id       VARCHAR(20) NOT NULL,   -- natural key (not unique in this table)
    name              VARCHAR(200) NOT NULL,
    email             VARCHAR(255) NOT NULL,
    city              VARCHAR(100),
    state             VARCHAR(2),
    segment           VARCHAR(50),
    -- SCD Type 2 metadata
    effective_date    DATE NOT NULL,
    expiration_date   DATE NOT NULL DEFAULT '9999-12-31',
    is_current        BOOLEAN NOT NULL DEFAULT TRUE,
    version           INT NOT NULL DEFAULT 1
);

CREATE INDEX idx_dim_cust_natural ON dim_customer_type2(customer_id);
CREATE INDEX idx_dim_cust_current ON dim_customer_type2(customer_id) WHERE is_current = TRUE;
```

### Type 2 Update Process

```sql
-- Step 1: Close the current record
UPDATE dim_customer_type2
SET expiration_date = CURRENT_DATE - INTERVAL '1 day',
    is_current = FALSE
WHERE customer_id = 'C-1001'
  AND is_current = TRUE;

-- Step 2: Insert the new version
INSERT INTO dim_customer_type2
    (customer_id, name, email, city, state, segment, effective_date, expiration_date, is_current, version)
SELECT
    'C-1001',
    name,                    -- unchanged
    'jane.new@example.com',  -- updated email
    'Denver',                -- updated city
    'CO',                    -- updated state
    segment,                 -- unchanged
    CURRENT_DATE,
    '9999-12-31',
    TRUE,
    version + 1
FROM dim_customer_type2
WHERE customer_id = 'C-1001'
  AND expiration_date = CURRENT_DATE - INTERVAL '1 day';
```

### Type 2 Merge Pattern (PostgreSQL)

```sql
-- Atomic merge using a staging table
WITH changes AS (
    SELECT
        s.customer_id,
        s.name,
        s.email,
        s.city,
        s.state,
        s.segment
    FROM staging_customers s
    INNER JOIN dim_customer_type2 d
        ON s.customer_id = d.customer_id
        AND d.is_current = TRUE
    WHERE s.name != d.name
       OR s.email != d.email
       OR s.city != d.city
       OR s.state != d.state
       OR s.segment != d.segment
),
-- Close existing records
closed AS (
    UPDATE dim_customer_type2 d
    SET expiration_date = CURRENT_DATE - INTERVAL '1 day',
        is_current = FALSE
    FROM changes c
    WHERE d.customer_id = c.customer_id
      AND d.is_current = TRUE
    RETURNING d.customer_id, d.version
)
-- Insert new versions
INSERT INTO dim_customer_type2
    (customer_id, name, email, city, state, segment, effective_date, expiration_date, is_current, version)
SELECT
    c.customer_id,
    c.name,
    c.email,
    c.city,
    c.state,
    c.segment,
    CURRENT_DATE,
    '9999-12-31',
    TRUE,
    cl.version + 1
FROM changes c
INNER JOIN closed cl ON c.customer_id = cl.customer_id;
```

### Querying Type 2 Dimensions

```sql
-- Current state of all customers
SELECT * FROM dim_customer_type2 WHERE is_current = TRUE;

-- Customer state as of a specific date
SELECT *
FROM dim_customer_type2
WHERE customer_id = 'C-1001'
  AND effective_date <= '2024-06-15'
  AND expiration_date >= '2024-06-15';

-- Fact query that respects historical dimension state
-- Each sale joins to the customer record that was active at that time
SELECT
    dd.year,
    dc.city,
    dc.state,
    SUM(fs.net_amount) AS revenue
FROM fact_sales fs
INNER JOIN dim_customer_type2 dc ON fs.customer_key = dc.customer_key
INNER JOIN dim_date dd ON fs.date_key = dd.date_key
GROUP BY dd.year, dc.city, dc.state;
-- Because fact_sales stores customer_key (surrogate), it naturally points
-- to the correct historical version of the customer
```

## SCD Type 3: Add New Column

Store the previous value in a separate column. Tracks only one prior version.

```sql
CREATE TABLE dim_customer_type3 (
    customer_key       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id        VARCHAR(20) NOT NULL UNIQUE,
    name               VARCHAR(200) NOT NULL,
    -- Current and previous for tracked attribute
    current_city       VARCHAR(100),
    previous_city      VARCHAR(100),
    current_state      VARCHAR(2),
    previous_state     VARCHAR(2),
    city_change_date   DATE,
    segment            VARCHAR(50)
);

-- Customer moves from Portland, OR to Denver, CO
UPDATE dim_customer_type3
SET previous_city = current_city,
    previous_state = current_state,
    current_city = 'Denver',
    current_state = 'CO',
    city_change_date = CURRENT_DATE
WHERE customer_id = 'C-1001';

-- Query: compare current vs previous
SELECT
    customer_id,
    name,
    current_city || ', ' || current_state AS current_location,
    previous_city || ', ' || previous_state AS previous_location,
    city_change_date
FROM dim_customer_type3
WHERE previous_city IS NOT NULL;
```

**When to use Type 3**:
- Only need to compare "current" vs "previous" (not full history)
- Organizational restructuring (current vs previous department)
- Simpler than Type 2 when one level of history suffices

## SCD Type 4: History Table

Current values in the main table, full history in a separate mini-dimension table.

```sql
-- Main dimension: always current
CREATE TABLE dim_customer_current (
    customer_key    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id     VARCHAR(20) NOT NULL UNIQUE,
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    city            VARCHAR(100),
    state           VARCHAR(2),
    segment         VARCHAR(50)
);

-- History table: all versions
CREATE TABLE dim_customer_history (
    customer_history_key  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id           VARCHAR(20) NOT NULL,
    name                  VARCHAR(200) NOT NULL,
    email                 VARCHAR(255) NOT NULL,
    city                  VARCHAR(100),
    state                 VARCHAR(2),
    segment               VARCHAR(50),
    effective_date        DATE NOT NULL,
    expiration_date       DATE NOT NULL DEFAULT '9999-12-31',
    change_reason         VARCHAR(200)
);

CREATE INDEX idx_cust_hist_id ON dim_customer_history(customer_id, effective_date);

-- Update process: update current + insert history
BEGIN;
    -- Archive current state to history
    INSERT INTO dim_customer_history
        (customer_id, name, email, city, state, segment, effective_date, expiration_date, change_reason)
    SELECT
        customer_id, name, email, city, state, segment,
        (SELECT COALESCE(MAX(effective_date), '1900-01-01') FROM dim_customer_history WHERE customer_id = 'C-1001'),
        CURRENT_DATE - INTERVAL '1 day',
        'Address change'
    FROM dim_customer_current
    WHERE customer_id = 'C-1001';

    -- Update current table
    UPDATE dim_customer_current
    SET city = 'Denver', state = 'CO'
    WHERE customer_id = 'C-1001';

    -- Insert new history record
    INSERT INTO dim_customer_history
        (customer_id, name, email, city, state, segment, effective_date, change_reason)
    SELECT customer_id, name, email, city, state, segment, CURRENT_DATE, 'Address change'
    FROM dim_customer_current
    WHERE customer_id = 'C-1001';
COMMIT;
```

**When to use Type 4**:
- Current-state queries are far more frequent than historical queries
- History table can be stored separately or archived
- Rapidly changing attributes that would bloat a Type 2 dimension

## SCD Type 6: Hybrid (1 + 2 + 3 Combined)

Combines Type 1 overwrite, Type 2 versioned rows, and Type 3 previous-value columns.

```sql
CREATE TABLE dim_customer_type6 (
    customer_key         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id          VARCHAR(20) NOT NULL,
    name                 VARCHAR(200) NOT NULL,
    -- Type 2 versioned attributes
    historical_city      VARCHAR(100),     -- value as of this row's effective_date
    historical_state     VARCHAR(2),
    -- Type 1/3 current-value columns (updated on ALL rows)
    current_city         VARCHAR(100),
    current_state        VARCHAR(2),
    -- Type 2 metadata
    effective_date       DATE NOT NULL,
    expiration_date      DATE NOT NULL DEFAULT '9999-12-31',
    is_current           BOOLEAN NOT NULL DEFAULT TRUE
);

-- Customer moves from Portland, OR to Denver, CO
BEGIN;
    -- Step 1: Close current record (Type 2)
    UPDATE dim_customer_type6
    SET expiration_date = CURRENT_DATE - INTERVAL '1 day',
        is_current = FALSE,
        -- Type 1: update current columns on old rows too
        current_city = 'Denver',
        current_state = 'CO'
    WHERE customer_id = 'C-1001'
      AND is_current = TRUE;

    -- Step 2: Update current columns on ALL historical rows (Type 1)
    UPDATE dim_customer_type6
    SET current_city = 'Denver',
        current_state = 'CO'
    WHERE customer_id = 'C-1001';

    -- Step 3: Insert new version (Type 2)
    INSERT INTO dim_customer_type6
        (customer_id, name, historical_city, historical_state, current_city, current_state,
         effective_date, expiration_date, is_current)
    VALUES
        ('C-1001', 'Jane Smith', 'Denver', 'CO', 'Denver', 'CO',
         CURRENT_DATE, '9999-12-31', TRUE);
COMMIT;

-- Query advantage: get both historical and current context in one join
SELECT
    dd.year,
    dc.historical_city AS city_at_time_of_sale,
    dc.current_city AS city_now,
    SUM(fs.net_amount) AS revenue
FROM fact_sales fs
INNER JOIN dim_customer_type6 dc ON fs.customer_key = dc.customer_key
INNER JOIN dim_date dd ON fs.date_key = dd.date_key
WHERE dc.customer_id = 'C-1001'
GROUP BY dd.year, dc.historical_city, dc.current_city;
```

## SCD Type Comparison

| Type | History Preserved? | Storage Cost | Complexity | Best For |
|------|-------------------|-------------|------------|----------|
| **0** | Immutable | Lowest | Simplest | Birth dates, registration dates |
| **1** | No | Low | Simple | Error corrections, irrelevant changes |
| **2** | Full | High (row per change) | Moderate | Most analytical use cases |
| **3** | One prior version | Low | Low | Before/after comparisons |
| **4** | Full (separate table) | Moderate | Moderate | Rapidly changing attributes |
| **6** | Full + current on all rows | Highest | Most complex | Need both historical and current in queries |

## Choosing the Right SCD Type

1. **Do you need any history at all?** No -> Type 1
2. **Is this attribute truly immutable?** Yes -> Type 0
3. **Do you only need current vs previous?** Yes -> Type 3
4. **Does the attribute change very frequently?** Yes -> Type 4 (separate history)
5. **Do queries often need both historical and current values?** Yes -> Type 6
6. **Default for most analytical tracking** -> Type 2

## Mixed SCD Types on One Table

In practice, different columns in the same dimension use different SCD types.

```sql
-- dim_employee with mixed SCD types
CREATE TABLE dim_employee (
    employee_key     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id      VARCHAR(20) NOT NULL,
    -- Type 0: never changes
    hire_date        DATE NOT NULL,
    -- Type 1: overwrite (corrections only)
    name             VARCHAR(200) NOT NULL,
    -- Type 2: full history
    department       VARCHAR(100) NOT NULL,
    job_title        VARCHAR(100) NOT NULL,
    salary_band      VARCHAR(20),
    -- Type 3: current + previous
    current_manager  VARCHAR(200),
    previous_manager VARCHAR(200),
    -- SCD Type 2 metadata
    effective_date   DATE NOT NULL,
    expiration_date  DATE NOT NULL DEFAULT '9999-12-31',
    is_current       BOOLEAN NOT NULL DEFAULT TRUE
);

-- When department changes: new row (Type 2), name stays (Type 1 if corrected)
-- When manager changes: update current_manager, shift old to previous_manager (Type 3)
-- hire_date is never modified (Type 0)
```
