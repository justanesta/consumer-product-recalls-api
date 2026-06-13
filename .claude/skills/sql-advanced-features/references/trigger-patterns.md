# Trigger Patterns

## BEFORE Triggers — Validation and Modification

```sql
-- PostgreSQL: validate and normalize data before insert/update
CREATE OR REPLACE FUNCTION validate_employee()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    -- Normalize email to lowercase
    NEW.email := LOWER(TRIM(NEW.email));

    -- Validate salary range by department
    IF NEW.salary < 0 THEN
        RAISE EXCEPTION 'Salary cannot be negative: %', NEW.salary;
    END IF;

    IF NEW.salary > (
        SELECT max_salary FROM department_salary_bands
        WHERE department_id = NEW.department_id
    ) THEN
        RAISE EXCEPTION 'Salary % exceeds department maximum', NEW.salary;
    END IF;

    -- Auto-set updated_at timestamp
    NEW.updated_at := NOW();

    RETURN NEW;  -- RETURN NEW to allow the operation; RETURN NULL to cancel
END;
$$;

CREATE TRIGGER trg_validate_employee
    BEFORE INSERT OR UPDATE ON employees
    FOR EACH ROW EXECUTE FUNCTION validate_employee();
```

## AFTER Triggers — Side Effects and Logging

```sql
-- PostgreSQL: maintain a running balance after each transaction
CREATE OR REPLACE FUNCTION update_account_balance()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE accounts
        SET balance = balance + NEW.amount
        WHERE account_id = NEW.account_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE accounts
        SET balance = balance - OLD.amount
        WHERE account_id = OLD.account_id;
    ELSIF TG_OP = 'UPDATE' THEN
        -- Reverse old amount, apply new amount
        UPDATE accounts
        SET balance = balance - OLD.amount + NEW.amount
        WHERE account_id = NEW.account_id;
    END IF;

    RETURN NULL;  -- AFTER triggers return value is ignored
END;
$$;

CREATE TRIGGER trg_update_balance
    AFTER INSERT OR UPDATE OR DELETE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_account_balance();
```

## INSTEAD OF Triggers — Updatable Complex Views

```sql
-- PostgreSQL: make a joined view updatable
CREATE VIEW v_employee_department AS
SELECT
    e.employee_id,
    e.first_name,
    e.last_name,
    e.salary,
    d.department_id,
    d.department_name
FROM employees e
INNER JOIN departments d ON e.department_id = d.department_id;

CREATE OR REPLACE FUNCTION v_employee_dept_insert()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_dept_id INTEGER;
BEGIN
    -- Look up or create the department
    SELECT department_id INTO v_dept_id
    FROM departments WHERE department_name = NEW.department_name;

    IF v_dept_id IS NULL THEN
        INSERT INTO departments (department_name)
        VALUES (NEW.department_name)
        RETURNING department_id INTO v_dept_id;
    END IF;

    INSERT INTO employees (first_name, last_name, salary, department_id)
    VALUES (NEW.first_name, NEW.last_name, NEW.salary, v_dept_id);

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_v_employee_dept_insert
    INSTEAD OF INSERT ON v_employee_department
    FOR EACH ROW EXECUTE FUNCTION v_employee_dept_insert();

-- Now you can insert through the view
INSERT INTO v_employee_department (first_name, last_name, salary, department_name)
VALUES ('Alice', 'Johnson', 85000, 'Engineering');
```

## Row-Level vs Statement-Level Triggers

```sql
-- ROW-LEVEL: fires once per affected row
CREATE TRIGGER trg_row_audit
    AFTER UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION log_order_change();

-- STATEMENT-LEVEL: fires once per SQL statement, regardless of row count
CREATE OR REPLACE FUNCTION notify_bulk_update()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO admin_notifications (message, created_at)
    VALUES (
        format('Bulk %s on %I: statement completed', TG_OP, TG_TABLE_NAME),
        NOW()
    );
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_statement_audit
    AFTER UPDATE ON orders
    FOR EACH STATEMENT EXECUTE FUNCTION notify_bulk_update();

-- Execution order for: UPDATE orders SET status = 'shipped' WHERE region = 'West';
-- 1. BEFORE STATEMENT triggers fire (once)
-- 2. For each row:
--    a. BEFORE ROW trigger fires
--    b. Row is updated
--    c. AFTER ROW trigger fires
-- 3. AFTER STATEMENT triggers fire (once)
```

## Comprehensive Audit Trail

```sql
-- Generic audit trigger reusable across tables
CREATE TABLE audit_log (
    audit_id BIGSERIAL PRIMARY KEY, table_name TEXT NOT NULL,
    operation TEXT NOT NULL, row_id TEXT,
    old_values JSONB, new_values JSONB,
    changed_by TEXT DEFAULT current_user, changed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION generic_audit_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE v_old JSONB; v_new JSONB;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN v_old := to_jsonb(OLD); END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN v_new := to_jsonb(NEW); END IF;

    -- For UPDATE, only store changed columns
    IF TG_OP = 'UPDATE' THEN
        v_old := (SELECT jsonb_object_agg(key, value) FROM jsonb_each(to_jsonb(OLD))
                  WHERE to_jsonb(OLD)->key IS DISTINCT FROM to_jsonb(NEW)->key);
        v_new := (SELECT jsonb_object_agg(key, value) FROM jsonb_each(to_jsonb(NEW))
                  WHERE to_jsonb(OLD)->key IS DISTINCT FROM to_jsonb(NEW)->key);
    END IF;

    INSERT INTO audit_log (table_name, operation, row_id, old_values, new_values)
    VALUES (TG_TABLE_NAME, TG_OP, COALESCE(NEW.id, OLD.id)::TEXT, v_old, v_new);
    RETURN COALESCE(NEW, OLD);
END;
$$;

-- Attach to any table
CREATE TRIGGER trg_audit_orders
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION generic_audit_trigger();
```

## Soft Delete Trigger

```sql
-- Intercept DELETE and convert to soft delete (RETURN NULL cancels actual DELETE)
CREATE OR REPLACE FUNCTION soft_delete_trigger() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE format('UPDATE %I.%I SET deleted_at = NOW(), deleted_by = current_user WHERE id = $1',
        TG_TABLE_SCHEMA, TG_TABLE_NAME) USING OLD.id;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_soft_delete_orders
    BEFORE DELETE ON orders FOR EACH ROW EXECUTE FUNCTION soft_delete_trigger();
```

## MySQL Trigger Syntax

```sql
-- MySQL: BEFORE INSERT trigger
DELIMITER //
CREATE TRIGGER trg_before_insert_employee
BEFORE INSERT ON employees FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
    SET NEW.created_at = NOW();
    IF NEW.salary < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Salary cannot be negative';
    END IF;
END //
DELIMITER ;

-- MySQL: AFTER UPDATE audit trigger
DELIMITER //
CREATE TRIGGER trg_after_update_orders
AFTER UPDATE ON orders FOR EACH ROW
BEGIN
    IF OLD.status != NEW.status THEN
        INSERT INTO order_audit (order_id, field_name, old_value, new_value, changed_at)
        VALUES (OLD.order_id, 'status', OLD.status, NEW.status, NOW());
    END IF;
END //
DELIMITER ;

-- MySQL limitations:
-- No statement-level triggers, no INSTEAD OF triggers
-- MySQL 8.0+ supports trigger ordering: FOLLOWS / PRECEDES
```

## SQL Server Trigger Syntax

```sql
-- SQL Server: AFTER trigger using inserted/deleted pseudo-tables
CREATE OR ALTER TRIGGER trg_order_audit ON dbo.orders
AFTER INSERT, UPDATE, DELETE AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.order_audit_log (order_id, operation, old_status, new_status, changed_at)
    SELECT COALESCE(i.order_id, d.order_id),
        CASE WHEN i.order_id IS NOT NULL AND d.order_id IS NOT NULL THEN 'UPDATE'
             WHEN i.order_id IS NOT NULL THEN 'INSERT' ELSE 'DELETE' END,
        d.status, i.status, GETDATE()
    FROM inserted i FULL OUTER JOIN deleted d ON i.order_id = d.order_id;
END;
GO

-- SQL Server: INSTEAD OF trigger on a view
CREATE OR ALTER TRIGGER trg_instead_of_insert_v_emp ON dbo.v_employee_department
INSTEAD OF INSERT AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.employees (first_name, last_name, salary, department_id)
    SELECT i.first_name, i.last_name, i.salary, d.department_id
    FROM inserted i INNER JOIN dbo.departments d ON i.department_name = d.department_name;
END;
GO
```

## Trigger Ordering and Disabling

```sql
-- PostgreSQL: triggers fire alphabetically — use numeric prefixes for ordering
CREATE TRIGGER trg_01_validate BEFORE INSERT ON orders ...;
CREATE TRIGGER trg_02_normalize BEFORE INSERT ON orders ...;

-- Disable triggers during bulk loads, re-enable after
ALTER TABLE orders DISABLE TRIGGER trg_01_validate;
ALTER TABLE orders ENABLE TRIGGER trg_01_validate;
ALTER TABLE orders DISABLE TRIGGER ALL;  -- disable all on table

-- SQL Server
DISABLE TRIGGER trg_order_audit ON dbo.orders;
ENABLE TRIGGER trg_order_audit ON dbo.orders;
```

## Trigger Performance Considerations

```
1. Keep trigger logic minimal — offload heavy work to async queues
2. Avoid triggers that call triggers (cascading triggers)
3. Never do network calls or external I/O in triggers
4. For high-throughput tables, consider:
   - Statement-level triggers instead of row-level
   - Change Data Capture (CDC) instead of triggers
   - Logical replication or event streaming (Debezium)
5. Disable triggers during bulk data loads and re-enable after
6. Audit triggers writing to a separate tablespace reduce contention
```
