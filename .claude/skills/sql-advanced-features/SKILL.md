---
name: sql-advanced-features
description: |
  Database object patterns for views, stored procedures, functions, triggers, transactions,
  and dynamic SQL. Use this skill when designing database logic, managing data integrity with
  transactions, building reusable SQL components, or implementing audit and automation patterns.
  Covers views, materialized views, stored procedures, UDFs, triggers, transaction isolation,
  locking strategies, and dynamic SQL across PostgreSQL, MySQL, and SQL Server.
---

# SQL Advanced Features

Essential patterns for database objects, procedural logic, and transaction management.

## Core Principles

1. **Push logic close to the data** - Views, procedures, and functions reduce network round-trips and enforce consistency
2. **Wrap multi-step operations in transactions** - Guarantee atomicity for related changes
3. **Prefer declarative over procedural** - Use set-based SQL before resorting to cursors or loops
4. **Parameterize all dynamic SQL** - Never concatenate user input into SQL strings
5. **Design for concurrency** - Choose the weakest isolation level that guarantees correctness

## Views

```sql
-- Encapsulate business logic in a reusable view
CREATE OR REPLACE VIEW active_customer_orders AS
SELECT
    c.customer_id,
    c.customer_name,
    c.email,
    o.order_id,
    o.order_date,
    o.total_amount,
    SUM(o.total_amount) OVER (PARTITION BY c.customer_id) AS lifetime_value
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
WHERE c.status = 'active'
  AND o.order_date >= CURRENT_DATE - INTERVAL '1 year';
```

See [view-patterns.md](references/view-patterns.md) for:
- Simple and complex view definitions
- Updatable views and WITH CHECK OPTION
- Security-barrier views and row-level access
- View dependency management

## Materialized Views

```sql
-- Pre-compute expensive aggregations
CREATE MATERIALIZED VIEW monthly_revenue_summary AS
SELECT
    DATE_TRUNC('month', order_date) AS revenue_month,
    product_category,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue,
    AVG(total_amount) AS avg_order_value
FROM orders o
INNER JOIN products p ON o.product_id = p.product_id
WHERE order_status = 'completed'
GROUP BY DATE_TRUNC('month', order_date), product_category
WITH DATA;

CREATE UNIQUE INDEX idx_monthly_rev ON monthly_revenue_summary (revenue_month, product_category);
```

See [materialized-view-patterns.md](references/materialized-view-patterns.md) for:
- Refresh strategies (full, concurrent, incremental)
- Auto-refresh with pg_cron and scheduled jobs
- Indexed materialized views (SQL Server)

## Stored Procedures

```sql
-- PostgreSQL: Transfer funds with validation and error handling
CREATE OR REPLACE PROCEDURE transfer_funds(
    p_from_account INTEGER, p_to_account INTEGER, p_amount NUMERIC
)
LANGUAGE plpgsql AS $$
DECLARE v_balance NUMERIC;
BEGIN
    SELECT balance INTO v_balance
    FROM accounts WHERE account_id = p_from_account FOR UPDATE;

    IF v_balance IS NULL THEN
        RAISE EXCEPTION 'Source account % not found', p_from_account;
    END IF;
    IF v_balance < p_amount THEN
        RAISE EXCEPTION 'Insufficient funds: available %, requested %', v_balance, p_amount;
    END IF;

    UPDATE accounts SET balance = balance - p_amount WHERE account_id = p_from_account;
    UPDATE accounts SET balance = balance + p_amount WHERE account_id = p_to_account;
    COMMIT;
END;
$$;
```

See [stored-procedure-patterns.md](references/stored-procedure-patterns.md) for:
- Parameter modes (IN, OUT, INOUT)
- Error handling and TRY/CATCH across databases
- Cursor usage and when to avoid cursors
- Transaction control inside procedures

## User-Defined Functions

```sql
-- Scalar function: calculate business days between two dates
CREATE OR REPLACE FUNCTION business_days_between(p_start DATE, p_end DATE)
RETURNS INTEGER LANGUAGE sql IMMUTABLE AS $$
    SELECT COUNT(*)::INTEGER
    FROM generate_series(p_start, p_end - 1, '1 day'::interval) d
    WHERE EXTRACT(DOW FROM d) NOT IN (0, 6);
$$;

SELECT order_id, business_days_between(order_date, ship_date) AS fulfillment_days
FROM orders;
```

See [function-patterns.md](references/function-patterns.md) for:
- Scalar vs table-valued vs aggregate functions
- Volatility categories (IMMUTABLE, STABLE, VOLATILE)
- Inline table-valued functions for performance
- Cross-database function syntax

## Triggers

```sql
-- Audit trail trigger: log all changes to the orders table
CREATE OR REPLACE FUNCTION audit_order_changes()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO order_audit_log (
        order_id, action, changed_by, changed_at,
        old_values, new_values
    ) VALUES (
        COALESCE(NEW.order_id, OLD.order_id),
        TG_OP,
        current_user,
        NOW(),
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN row_to_json(OLD) END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN row_to_json(NEW) END
    );
    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER trg_order_audit
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION audit_order_changes();
```

See [trigger-patterns.md](references/trigger-patterns.md) for:
- BEFORE vs AFTER vs INSTEAD OF triggers
- Row-level vs statement-level triggers
- Audit trail and soft-delete patterns
- Trigger ordering and performance

## Transactions and Locking

```sql
-- Explicit transaction with savepoints for partial rollback
BEGIN;
SAVEPOINT before_inventory;
UPDATE inventory SET quantity = quantity - 5 WHERE product_id = 101;

-- Roll back only the inventory change if quantity went negative
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM inventory WHERE product_id = 101 AND quantity < 0) THEN
        ROLLBACK TO SAVEPOINT before_inventory;
    END IF;
END $$;

INSERT INTO order_items (order_id, product_id, quantity) VALUES (5001, 101, 5);
COMMIT;
```

See [transaction-patterns.md](references/transaction-patterns.md) for:
- Isolation levels (READ COMMITTED through SERIALIZABLE)
- Deadlock prevention and detection
- Optimistic vs pessimistic locking strategies
- Distributed transaction patterns

## Dynamic SQL

```sql
-- Safe parameterized dynamic SQL for flexible search
CREATE OR REPLACE FUNCTION search_products(
    p_name TEXT DEFAULT NULL, p_category TEXT DEFAULT NULL,
    p_min_price NUMERIC DEFAULT NULL, p_max_price NUMERIC DEFAULT NULL
) RETURNS SETOF products
LANGUAGE plpgsql AS $$
DECLARE v_sql TEXT := 'SELECT * FROM products WHERE 1=1';
BEGIN
    IF p_name IS NOT NULL THEN v_sql := v_sql || ' AND product_name ILIKE $1'; END IF;
    IF p_category IS NOT NULL THEN v_sql := v_sql || ' AND category = $2'; END IF;
    IF p_min_price IS NOT NULL THEN v_sql := v_sql || ' AND price >= $3'; END IF;
    IF p_max_price IS NOT NULL THEN v_sql := v_sql || ' AND price <= $4'; END IF;

    RETURN QUERY EXECUTE v_sql
        USING '%' || p_name || '%', p_category, p_min_price, p_max_price;
END;
$$;
```

See [dynamic-sql-patterns.md](references/dynamic-sql-patterns.md) for:
- Parameterized queries vs string concatenation
- SQL injection prevention techniques
- EXECUTE IMMEDIATE and sp_executesql patterns
- Dynamic pivot and table-name construction

## Cross-Database Compatibility

| Feature | PostgreSQL | MySQL | SQL Server |
|---------|-----------|-------|------------|
| Create procedure | `CREATE PROCEDURE ... LANGUAGE plpgsql` | `CREATE PROCEDURE ... BEGIN ... END` | `CREATE PROCEDURE ... AS BEGIN ... END` |
| Temp tables in procs | `CREATE TEMP TABLE` | `CREATE TEMPORARY TABLE` | `CREATE TABLE #temp` |
| Error handling | `EXCEPTION WHEN ... THEN` | `DECLARE HANDLER FOR ...` | `BEGIN TRY ... BEGIN CATCH` |
| Output params | `OUT` parameter | `OUT` parameter | `@param OUTPUT` |
| Mat view refresh | `REFRESH MATERIALIZED VIEW` | Not native (use tables) | Indexed views (auto-refresh) |
| Dynamic SQL | `EXECUTE ... USING` | `PREPARE` / `EXECUTE` | `sp_executesql @sql, @params` |
| Trigger syntax | `CREATE TRIGGER ... EXECUTE FUNCTION` | `CREATE TRIGGER ... FOR EACH ROW` | `CREATE TRIGGER ... ON table AFTER` |
| Isolation default | READ COMMITTED | REPEATABLE READ (InnoDB) | READ COMMITTED |

## Anti-Patterns to Avoid

| Avoid | Use Instead | Why |
|-------|-------------|-----|
| String concatenation in dynamic SQL | Parameterized queries (`USING`, `sp_executesql`) | SQL injection vulnerability |
| Cursors for set-based operations | Single UPDATE/INSERT with joins | Orders of magnitude slower |
| Triggers that call triggers | Explicit procedure calls or event queues | Cascade debugging nightmare |
| `SELECT *` inside views | Explicit column lists | Schema changes silently break consumers |
| Long-running transactions | Smaller batches with retry logic | Lock escalation and blocking |
| `SERIALIZABLE` as default isolation | `READ COMMITTED` with explicit locking where needed | Unnecessary contention and deadlocks |
| Nested dynamic SQL | Refactor into separate functions | Unreadable and unmaintainable |

## Performance Tips

- Index materialized views on columns used in WHERE and JOIN clauses
- Use `STABLE` or `IMMUTABLE` volatility on functions so the planner can optimize calls
- Prefer inline table-valued functions over multi-statement TVFs (SQL Server) for plan inlining
- Keep transactions short: acquire locks late, release early
- Batch large DML operations (UPDATE/DELETE in chunks of 5,000-10,000 rows) to avoid lock escalation
- Avoid triggers on high-throughput tables; use change data capture or async processing instead
- Use `EXPLAIN ANALYZE` to verify that views are not hiding expensive query plans

source: PostgreSQL docs, MySQL docs, SQL Server docs, Oracle docs, database internals references
