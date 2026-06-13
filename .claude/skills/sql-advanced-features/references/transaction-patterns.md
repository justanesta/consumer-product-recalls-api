# Transaction Patterns

## Basic Transaction Structure

```sql
-- PostgreSQL / standard SQL
BEGIN;
    INSERT INTO orders (customer_id, order_date, total_amount)
    VALUES (101, CURRENT_DATE, 250.00);

    INSERT INTO order_items (order_id, product_id, quantity, line_total)
    VALUES (currval('orders_order_id_seq'), 42, 5, 250.00);

    UPDATE inventory SET quantity = quantity - 5 WHERE product_id = 42;
COMMIT;

-- SQL Server
BEGIN TRANSACTION;
    INSERT INTO orders (customer_id, order_date, total_amount)
    VALUES (101, GETDATE(), 250.00);

    DECLARE @oid INT = SCOPE_IDENTITY();

    INSERT INTO order_items (order_id, product_id, quantity, line_total)
    VALUES (@oid, 42, 5, 250.00);

    UPDATE inventory SET quantity = quantity - 5 WHERE product_id = 42;
COMMIT TRANSACTION;

-- MySQL (InnoDB)
START TRANSACTION;
    INSERT INTO orders (customer_id, order_date, total_amount)
    VALUES (101, CURDATE(), 250.00);

    SET @oid = LAST_INSERT_ID();

    INSERT INTO order_items (order_id, product_id, quantity, line_total)
    VALUES (@oid, 42, 5, 250.00);

    UPDATE inventory SET quantity = quantity - 5 WHERE product_id = 42;
COMMIT;
```

## Isolation Levels

```sql
-- READ UNCOMMITTED: can see uncommitted changes from other transactions (dirty reads)
-- Rarely used except for approximate monitoring queries
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

-- READ COMMITTED (PostgreSQL/SQL Server default): sees only committed data
-- Each statement sees a fresh snapshot
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

-- REPEATABLE READ (MySQL InnoDB default): snapshot at start of transaction
-- Same SELECT returns same results throughout the transaction
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

-- SERIALIZABLE: strongest isolation, transactions behave as if executed one at a time
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN;
    SELECT SUM(balance) FROM accounts WHERE owner_id = 101;
    -- No other transaction can modify these rows until this commits
    UPDATE accounts SET balance = balance - 100 WHERE account_id = 1;
COMMIT;
```

## Isolation Level Comparison

```
| Phenomenon        | READ UNCOMMITTED | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|-------------------|------------------|----------------|-----------------|--------------|
| Dirty Read        | Possible         | Prevented      | Prevented       | Prevented    |
| Non-Repeatable    | Possible         | Possible       | Prevented       | Prevented    |
| Phantom Read      | Possible         | Possible       | Possible*       | Prevented    |
| Serialization     | Possible         | Possible       | Possible        | Prevented    |
| Anomaly           |                  |                |                 |              |

* PostgreSQL REPEATABLE READ also prevents phantom reads (uses MVCC snapshot isolation).
  MySQL REPEATABLE READ prevents phantoms for consistent reads but not for locking reads.
```

## Savepoints for Partial Rollback

```sql
-- Process multiple independent items; roll back only failures
BEGIN;

SAVEPOINT item_1;
INSERT INTO order_items (order_id, product_id, quantity) VALUES (5001, 101, 2);
UPDATE inventory SET quantity = quantity - 2 WHERE product_id = 101;
-- Check: did inventory go negative?
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM inventory WHERE product_id = 101 AND quantity < 0) THEN
        RAISE NOTICE 'Product 101 out of stock, skipping';
        ROLLBACK TO SAVEPOINT item_1;
    ELSE
        RELEASE SAVEPOINT item_1;
    END IF;
END $$;

SAVEPOINT item_2;
INSERT INTO order_items (order_id, product_id, quantity) VALUES (5001, 202, 1);
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 202;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM inventory WHERE product_id = 202 AND quantity < 0) THEN
        RAISE NOTICE 'Product 202 out of stock, skipping';
        ROLLBACK TO SAVEPOINT item_2;
    ELSE
        RELEASE SAVEPOINT item_2;
    END IF;
END $$;

-- Commit whatever succeeded
COMMIT;

-- SQL Server savepoint syntax
BEGIN TRANSACTION;
    SAVE TRANSACTION item_1;
    -- ... operations ...
    ROLLBACK TRANSACTION item_1;  -- partial rollback to savepoint
COMMIT TRANSACTION;
```

## Pessimistic Locking (SELECT FOR UPDATE)

```sql
-- Lock rows before modifying to prevent concurrent changes
BEGIN;

-- Lock the specific account row — other transactions block on this row
SELECT balance FROM accounts
WHERE account_id = 42
FOR UPDATE;

-- Safely modify knowing no one else can change it
UPDATE accounts SET balance = balance - 100 WHERE account_id = 42;

COMMIT;
-- Lock is released on COMMIT or ROLLBACK

-- SKIP LOCKED: skip rows that are already locked (job queue pattern)
BEGIN;
SELECT task_id, payload
FROM task_queue
WHERE status = 'pending'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;
-- Returns the next available unlocked task

UPDATE task_queue SET status = 'processing' WHERE task_id = ?;
COMMIT;

-- NOWAIT: fail immediately if row is locked (no waiting)
BEGIN;
SELECT * FROM accounts WHERE account_id = 42 FOR UPDATE NOWAIT;
-- ERROR: could not obtain lock on row (if another transaction holds it)
```

## Optimistic Locking (Version Column)

```sql
-- Add a version column to the table
ALTER TABLE products ADD COLUMN version INTEGER NOT NULL DEFAULT 1;

-- Application reads the current version
SELECT product_id, product_name, price, version
FROM products WHERE product_id = 42;
-- Returns: product_id=42, price=29.99, version=3

-- Update only if version hasn't changed
UPDATE products
SET price = 34.99, version = version + 1
WHERE product_id = 42 AND version = 3;

-- Check if the update succeeded
-- If 0 rows affected: someone else modified the row — retry or fail
-- If 1 row affected: success

-- Application retry logic: read version, attempt update, retry if 0 rows affected
-- If ROW_COUNT = 0 after the UPDATE, another transaction modified the row — retry or fail
```

## Deadlock Prevention

```sql
-- Deadlock scenario:
-- Transaction A: locks row 1, then tries to lock row 2
-- Transaction B: locks row 2, then tries to lock row 1
-- Result: deadlock — one transaction is rolled back

-- Prevention strategy 1: always lock rows in a consistent order
BEGIN;
-- Sort account IDs to ensure consistent locking order
SELECT * FROM accounts
WHERE account_id IN (42, 17)
ORDER BY account_id  -- always lock lower ID first
FOR UPDATE;

UPDATE accounts SET balance = balance - 100 WHERE account_id = 17;
UPDATE accounts SET balance = balance + 100 WHERE account_id = 42;
COMMIT;

-- Prevention strategy 2: use advisory locks
BEGIN;
-- Acquire an application-level lock (non-blocking check)
SELECT pg_try_advisory_xact_lock(hashtext('transfer:17:42'));
-- Returns TRUE if lock acquired, FALSE if already held
-- Lock automatically releases at end of transaction

-- Prevention strategy 3: use short transactions
-- Minimize the time between acquiring locks and committing

-- Prevention strategy 4: use NOWAIT to fail fast
BEGIN;
SELECT * FROM accounts WHERE account_id = 42 FOR UPDATE NOWAIT;
-- If locked, fails immediately instead of waiting and potentially deadlocking
```

## Batch Processing with Transactions

```sql
-- Process large deletes in batches to avoid lock escalation
CREATE OR REPLACE PROCEDURE batch_delete_old_logs(
    p_cutoff_date DATE,
    p_batch_size INTEGER DEFAULT 10000
)
LANGUAGE plpgsql AS $$
DECLARE
    v_deleted INTEGER;
    v_total INTEGER := 0;
BEGIN
    LOOP
        DELETE FROM application_logs
        WHERE log_id IN (
            SELECT log_id FROM application_logs
            WHERE log_date < p_cutoff_date
            LIMIT p_batch_size
        );

        GET DIAGNOSTICS v_deleted = ROW_COUNT;
        v_total := v_total + v_deleted;

        COMMIT;  -- release locks between batches
        RAISE NOTICE 'Deleted % rows (total: %)', v_deleted, v_total;

        EXIT WHEN v_deleted < p_batch_size;

        PERFORM pg_sleep(0.1);  -- brief pause to let other transactions through
    END LOOP;
END;
$$;
```

## Transaction Timeout and Monitoring

```sql
-- PostgreSQL: set statement and transaction timeouts
SET statement_timeout = '30s';
SET idle_in_transaction_session_timeout = '5min';

-- Find long-running transactions
SELECT pid, usename, state,
    NOW() - xact_start AS transaction_duration, query
FROM pg_stat_activity
WHERE state != 'idle' AND xact_start IS NOT NULL
ORDER BY xact_start;

-- Find blocked queries and their blockers
SELECT blocked.pid AS blocked_pid, blocked.query AS blocked_query,
    blocking.pid AS blocking_pid, blocking.query AS blocking_query
FROM pg_stat_activity blocked
JOIN pg_locks bl ON bl.pid = blocked.pid
JOIN pg_locks kl ON kl.locktype = bl.locktype
    AND kl.relation IS NOT DISTINCT FROM bl.relation AND kl.pid != bl.pid
JOIN pg_stat_activity blocking ON blocking.pid = kl.pid
WHERE NOT bl.granted;
```

## Optimistic vs Pessimistic Decision Guide

```
Use PESSIMISTIC locking (SELECT FOR UPDATE) when:
  - Conflicts are frequent (high contention)
  - The cost of retrying is high
  - Transactions are short-lived
  - You control the entire data access layer

Use OPTIMISTIC locking (version column) when:
  - Conflicts are rare (low contention)
  - Read-heavy workload with infrequent writes
  - Long user think-time between read and write
  - Distributed systems where locking across nodes is impractical
  - Web applications with stateless request handling
```
