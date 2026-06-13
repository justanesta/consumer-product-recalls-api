# Stored Procedure Patterns

## Basic Procedure with Parameters (PostgreSQL)

```sql
-- IN parameters (default), OUT parameters, and INOUT
CREATE OR REPLACE PROCEDURE create_order(
    IN  p_customer_id  INTEGER,
    IN  p_product_id   INTEGER,
    IN  p_quantity      INTEGER,
    OUT p_order_id      INTEGER,
    OUT p_total         NUMERIC
)
LANGUAGE plpgsql AS $$
DECLARE
    v_price NUMERIC;
BEGIN
    SELECT price INTO v_price FROM products WHERE product_id = p_product_id;

    IF v_price IS NULL THEN
        RAISE EXCEPTION 'Product % not found', p_product_id;
    END IF;

    p_total := v_price * p_quantity;

    INSERT INTO orders (customer_id, product_id, quantity, total_amount, order_date)
    VALUES (p_customer_id, p_product_id, p_quantity, p_total, CURRENT_DATE)
    RETURNING order_id INTO p_order_id;

    COMMIT;
END;
$$;

-- Call with OUT parameters
CALL create_order(101, 55, 3, NULL, NULL);
```

## MySQL Procedure Syntax

```sql
DELIMITER //

CREATE PROCEDURE sp_create_order(
    IN  p_customer_id INT,
    IN  p_product_id  INT,
    IN  p_quantity     INT,
    OUT p_order_id    INT,
    OUT p_total       DECIMAL(10,2)
)
BEGIN
    DECLARE v_price DECIMAL(10,2);

    SELECT price INTO v_price FROM products WHERE product_id = p_product_id;

    IF v_price IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Product not found';
    END IF;

    SET p_total = v_price * p_quantity;

    INSERT INTO orders (customer_id, product_id, quantity, total_amount, order_date)
    VALUES (p_customer_id, p_product_id, p_quantity, p_total, CURDATE());

    SET p_order_id = LAST_INSERT_ID();
END //

DELIMITER ;

-- Call in MySQL
CALL sp_create_order(101, 55, 3, @order_id, @total);
SELECT @order_id, @total;
```

## SQL Server Procedure Syntax

```sql
CREATE OR ALTER PROCEDURE dbo.sp_create_order
    @customer_id INT,
    @product_id  INT,
    @quantity     INT,
    @order_id    INT OUTPUT,
    @total       DECIMAL(10,2) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @price DECIMAL(10,2);

    SELECT @price = price FROM products WHERE product_id = @product_id;

    IF @price IS NULL
    BEGIN
        RAISERROR('Product %d not found', 16, 1, @product_id);
        RETURN;
    END

    SET @total = @price * @quantity;

    INSERT INTO orders (customer_id, product_id, quantity, total_amount, order_date)
    VALUES (@customer_id, @product_id, @quantity, @total, GETDATE());

    SET @order_id = SCOPE_IDENTITY();
END;
GO

-- Call in SQL Server
DECLARE @oid INT, @tot DECIMAL(10,2);
EXEC dbo.sp_create_order 101, 55, 3, @oid OUTPUT, @tot OUTPUT;
SELECT @oid AS order_id, @tot AS total;
```

## Error Handling Patterns

```sql
-- PostgreSQL: EXCEPTION block
CREATE OR REPLACE PROCEDURE safe_transfer(
    p_from_acct INTEGER,
    p_to_acct   INTEGER,
    p_amount    NUMERIC
)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE accounts SET balance = balance - p_amount WHERE account_id = p_from_acct;
    UPDATE accounts SET balance = balance + p_amount WHERE account_id = p_to_acct;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target account % does not exist', p_to_acct;
    END IF;

    COMMIT;
EXCEPTION
    WHEN numeric_value_out_of_range THEN
        ROLLBACK;
        RAISE NOTICE 'Amount % is out of range', p_amount;
    WHEN check_violation THEN
        ROLLBACK;
        RAISE NOTICE 'Balance constraint violated — insufficient funds';
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE NOTICE 'Unexpected error: % %', SQLSTATE, SQLERRM;
        RAISE;  -- re-raise after logging
END;
$$;

-- SQL Server: TRY/CATCH
CREATE OR ALTER PROCEDURE dbo.sp_safe_transfer
    @from_acct INT,
    @to_acct   INT,
    @amount    DECIMAL(12,2)
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE accounts SET balance = balance - @amount WHERE account_id = @from_acct;
        UPDATE accounts SET balance = balance + @amount WHERE account_id = @to_acct;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;

        DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @sev INT = ERROR_SEVERITY();
        DECLARE @state INT = ERROR_STATE();
        RAISERROR(@msg, @sev, @state);
    END CATCH
END;
GO

-- MySQL: DECLARE HANDLER
DELIMITER //
CREATE PROCEDURE sp_safe_transfer(
    IN p_from_acct INT,
    IN p_to_acct   INT,
    IN p_amount    DECIMAL(12,2)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;  -- re-raise the original error
    END;

    START TRANSACTION;
    UPDATE accounts SET balance = balance - p_amount WHERE account_id = p_from_acct;
    UPDATE accounts SET balance = balance + p_amount WHERE account_id = p_to_acct;
    COMMIT;
END //
DELIMITER ;
```

## Cursor Patterns

```sql
-- PostgreSQL: cursor for row-by-row processing (use sparingly)
CREATE OR REPLACE PROCEDURE recalculate_customer_tiers()
LANGUAGE plpgsql AS $$
DECLARE v_rec RECORD; v_batch INTEGER := 0;
    v_cursor CURSOR FOR
        SELECT customer_id, SUM(total_amount) AS spend
        FROM orders WHERE order_status = 'completed' GROUP BY customer_id;
BEGIN
    OPEN v_cursor;
    LOOP
        FETCH v_cursor INTO v_rec;
        EXIT WHEN NOT FOUND;
        UPDATE customers SET tier = CASE
            WHEN v_rec.spend >= 50000 THEN 'Platinum'
            WHEN v_rec.spend >= 10000 THEN 'Gold'
            WHEN v_rec.spend >= 1000 THEN 'Silver' ELSE 'Bronze' END
        WHERE customer_id = v_rec.customer_id;
        v_batch := v_batch + 1;
        IF v_batch % 1000 = 0 THEN COMMIT; END IF;
    END LOOP;
    CLOSE v_cursor; COMMIT;
END;
$$;

-- BETTER: set-based alternative (no cursor needed)
UPDATE customers c SET tier = CASE
    WHEN os.spend >= 50000 THEN 'Platinum' WHEN os.spend >= 10000 THEN 'Gold'
    WHEN os.spend >= 1000 THEN 'Silver' ELSE 'Bronze' END
FROM (SELECT customer_id, SUM(total_amount) AS spend
      FROM orders WHERE order_status = 'completed' GROUP BY customer_id) os
WHERE c.customer_id = os.customer_id;
```

## Transaction Control Inside Procedures

```sql
-- PostgreSQL: procedures can COMMIT/ROLLBACK (functions cannot)
-- Batch archive with periodic commits to avoid long-held locks
CREATE OR REPLACE PROCEDURE batch_archive_orders(p_cutoff_date DATE)
LANGUAGE plpgsql AS $$
DECLARE
    v_batch_size CONSTANT INTEGER := 5000;
    v_archived INTEGER;
BEGIN
    LOOP
        WITH to_archive AS (
            SELECT order_id FROM orders
            WHERE order_date < p_cutoff_date AND archived = FALSE
            LIMIT v_batch_size FOR UPDATE SKIP LOCKED
        )
        INSERT INTO orders_archive
        SELECT o.* FROM orders o INNER JOIN to_archive t ON o.order_id = t.order_id;

        GET DIAGNOSTICS v_archived = ROW_COUNT;
        EXIT WHEN v_archived = 0;

        COMMIT;  -- release locks between batches
    END LOOP;
END;
$$;
```

## Returning Result Sets

```sql
-- PostgreSQL: use a function (not procedure) to return a result set
CREATE OR REPLACE FUNCTION get_customer_orders(p_customer_id INTEGER)
RETURNS TABLE (order_id INTEGER, order_date DATE, total_amount NUMERIC, status TEXT)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT o.order_id, o.order_date, o.total_amount, o.status
    FROM orders o WHERE o.customer_id = p_customer_id ORDER BY o.order_date DESC;
END;
$$;

-- SQL Server: procedures return result sets directly
CREATE PROCEDURE dbo.sp_get_customer_orders @customer_id INT AS
BEGIN
    SET NOCOUNT ON;
    SELECT order_id, order_date, total_amount, status
    FROM orders WHERE customer_id = @customer_id ORDER BY order_date DESC;
END;
GO
```

## Procedure vs Function Decision Guide

```
Use a PROCEDURE when:
  - You need to COMMIT or ROLLBACK inside the body
  - The operation is a side effect (INSERT, UPDATE, DELETE)
  - You don't need to call it from SELECT
  - You need OUT parameters for multiple return values

Use a FUNCTION when:
  - You need to call it in SELECT, WHERE, or JOIN
  - You need to return a result set (table-valued function)
  - The operation is a pure computation with no side effects
  - You need composability in SQL expressions
```
