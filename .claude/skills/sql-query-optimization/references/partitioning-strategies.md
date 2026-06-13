# Partitioning Strategies

Guide to table partitioning for managing very large tables (typically 100M+ rows), improving query performance through partition pruning, and simplifying data lifecycle management.

## When to Partition

Partition a table when:
- The table exceeds 100M rows and queries consistently filter on a specific column
- You need to purge old data quickly (DROP partition is instant vs DELETE + VACUUM)
- Query performance degrades because indexes grow too large to fit in memory
- Maintenance operations (VACUUM, REINDEX) take too long on the full table

Do NOT partition when:
- The table has fewer than 10M rows -- overhead outweighs benefit
- Queries do not filter on the partition key -- all partitions get scanned
- You only need faster lookups -- an index is usually sufficient

## Range Partitioning

Divides rows into partitions based on a continuous range of values. Most common for time-series data.

```sql
-- PostgreSQL: declarative range partitioning on event_date
CREATE TABLE events (
    event_id    BIGSERIAL,
    event_date  DATE NOT NULL,
    event_type  TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    payload     JSONB
) PARTITION BY RANGE (event_date);

-- Create quarterly partitions
CREATE TABLE events_2025_q1 PARTITION OF events
    FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');
CREATE TABLE events_2025_q2 PARTITION OF events
    FOR VALUES FROM ('2025-04-01') TO ('2025-07-01');
CREATE TABLE events_2025_q3 PARTITION OF events
    FOR VALUES FROM ('2025-07-01') TO ('2025-10-01');
CREATE TABLE events_2025_q4 PARTITION OF events
    FOR VALUES FROM ('2025-10-01') TO ('2026-01-01');

-- Default partition catches rows that do not match any range
CREATE TABLE events_default PARTITION OF events DEFAULT;
```

```sql
-- SQL Server: partition function + scheme
CREATE PARTITION FUNCTION pf_event_date (DATE)
AS RANGE RIGHT FOR VALUES ('2025-04-01', '2025-07-01', '2025-10-01', '2026-01-01');

CREATE PARTITION SCHEME ps_event_date
AS PARTITION pf_event_date ALL TO ([PRIMARY]);

CREATE TABLE events (
    event_id    BIGINT IDENTITY,
    event_date  DATE NOT NULL,
    event_type  NVARCHAR(50),
    user_id     INT,
    payload     NVARCHAR(MAX)
) ON ps_event_date(event_date);
```

```sql
-- MySQL: range partitioning
CREATE TABLE events (
    event_id    BIGINT AUTO_INCREMENT,
    event_date  DATE NOT NULL,
    event_type  VARCHAR(50),
    user_id     INT,
    payload     JSON,
    PRIMARY KEY (event_id, event_date)
) PARTITION BY RANGE (YEAR(event_date) * 100 + MONTH(event_date)) (
    PARTITION p2025q1 VALUES LESS THAN (202504),
    PARTITION p2025q2 VALUES LESS THAN (202507),
    PARTITION p2025q3 VALUES LESS THAN (202510),
    PARTITION p2025q4 VALUES LESS THAN (202601),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);
-- Note: MySQL requires the partition key to be part of the primary key
```

## List Partitioning

Divides rows based on discrete values. Good for region, category, or status columns.

```sql
-- PostgreSQL: list partitioning by region
CREATE TABLE sales (
    sale_id     BIGSERIAL,
    sale_date   DATE NOT NULL,
    region      TEXT NOT NULL,
    amount      NUMERIC(12,2)
) PARTITION BY LIST (region);

CREATE TABLE sales_north_america PARTITION OF sales
    FOR VALUES IN ('US', 'CA', 'MX');
CREATE TABLE sales_europe PARTITION OF sales
    FOR VALUES IN ('GB', 'DE', 'FR', 'ES', 'IT');
CREATE TABLE sales_asia PARTITION OF sales
    FOR VALUES IN ('JP', 'CN', 'KR', 'IN');
CREATE TABLE sales_other PARTITION OF sales DEFAULT;
```

```sql
-- Query with partition pruning on list partition
EXPLAIN ANALYZE
SELECT * FROM sales
WHERE region IN ('US', 'CA') AND sale_date >= '2025-01-01';

-- Only scans sales_north_america, skips Europe, Asia, and other
-- Output shows: "Partitions selected: 1 out of 4"
```

## Hash Partitioning

Distributes rows evenly across partitions using a hash of the partition key. Useful for spreading I/O when there is no natural range or list boundary.

```sql
-- PostgreSQL: hash partitioning for even distribution
CREATE TABLE user_sessions (
    session_id  UUID NOT NULL,
    user_id     INTEGER NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL,
    data        JSONB
) PARTITION BY HASH (user_id);

CREATE TABLE user_sessions_p0 PARTITION OF user_sessions
    FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE user_sessions_p1 PARTITION OF user_sessions
    FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE user_sessions_p2 PARTITION OF user_sessions
    FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE user_sessions_p3 PARTITION OF user_sessions
    FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

Hash partitioning trades pruning ability for even distribution. Queries with `WHERE user_id = X` prune to one partition, but range queries on user_id scan all partitions.

## Partition Pruning

Partition pruning is the optimizer's ability to skip partitions that cannot contain matching rows. Verify pruning with EXPLAIN.

```sql
-- PostgreSQL: verify partition pruning
EXPLAIN (ANALYZE)
SELECT * FROM events
WHERE event_date BETWEEN '2025-02-01' AND '2025-02-28';

-- Expected output showing pruning:
-- Append  (actual time=0.02..45.3 rows=28400 loops=1)
--   Subplans Removed: 3          <-- 3 partitions pruned
--   -> Seq Scan on events_2025_q1
--        Filter: (event_date >= '2025-02-01' AND event_date <= '2025-02-28')
```

**Pruning requirements:**
- The WHERE clause must reference the partition key directly
- The predicate must be sargable (no functions wrapping the partition key)
- For parameterized queries, runtime pruning happens at execution time (PostgreSQL 11+)

```sql
-- PRUNING WORKS: direct comparison on partition key
WHERE event_date >= '2025-04-01' AND event_date < '2025-07-01'

-- PRUNING FAILS: function wraps the partition key
WHERE EXTRACT(YEAR FROM event_date) = 2025

-- PRUNING WORKS with JOINs (PostgreSQL 12+): runtime partition pruning
SELECT e.*
FROM events e
JOIN active_campaigns ac ON e.event_date = ac.campaign_date;
```

## Sub-Partitioning (Composite Partitioning)

Partition on two dimensions for very large datasets.

```sql
-- PostgreSQL: range partition by date, then list sub-partition by region
CREATE TABLE global_events (
    event_id    BIGSERIAL,
    event_date  DATE NOT NULL,
    region      TEXT NOT NULL,
    payload     JSONB
) PARTITION BY RANGE (event_date);

CREATE TABLE global_events_2025_q1 PARTITION OF global_events
    FOR VALUES FROM ('2025-01-01') TO ('2025-04-01')
    PARTITION BY LIST (region);

CREATE TABLE global_events_2025_q1_us PARTITION OF global_events_2025_q1
    FOR VALUES IN ('US');
CREATE TABLE global_events_2025_q1_eu PARTITION OF global_events_2025_q1
    FOR VALUES IN ('EU');
CREATE TABLE global_events_2025_q1_other PARTITION OF global_events_2025_q1
    DEFAULT;
```

## Partition Maintenance

### Adding New Partitions

```sql
-- PostgreSQL: add a new partition for the next quarter
CREATE TABLE events_2026_q1 PARTITION OF events
    FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');

-- If a DEFAULT partition exists, detach it first, add the new partition, reattach
BEGIN;
ALTER TABLE events DETACH PARTITION events_default;
CREATE TABLE events_2026_q1 PARTITION OF events
    FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');
-- Move any rows from default that belong in the new partition
INSERT INTO events_2026_q1
    SELECT * FROM events_default
    WHERE event_date >= '2026-01-01' AND event_date < '2026-04-01';
DELETE FROM events_default
    WHERE event_date >= '2026-01-01' AND event_date < '2026-04-01';
ALTER TABLE events ATTACH PARTITION events_default DEFAULT;
COMMIT;
```

### Dropping Old Partitions (Data Lifecycle)

```sql
-- PostgreSQL: instant data removal by dropping a partition
-- Much faster than DELETE + VACUUM on millions of rows
ALTER TABLE events DETACH PARTITION events_2024_q1;
DROP TABLE events_2024_q1;

-- SQL Server: switch partition out (instant, metadata-only)
ALTER TABLE events SWITCH PARTITION 1 TO events_archive;
TRUNCATE TABLE events_archive;
```

### Indexes on Partitioned Tables

```sql
-- PostgreSQL: create index on the parent; automatically applies to all partitions
CREATE INDEX idx_events_user_id ON events (user_id);
-- Each partition gets its own local index

-- Create index only on a specific partition
CREATE INDEX idx_events_2025_q1_type ON events_2025_q1 (event_type);

-- PostgreSQL 11+: CONCURRENTLY on partitioned tables
CREATE INDEX CONCURRENTLY idx_events_type ON events (event_type);
```

## Performance Considerations

```sql
-- Monitor partition sizes for balance
SELECT
    child.relname AS partition_name,
    pg_size_pretty(pg_relation_size(child.oid)) AS size,
    pg_stat_get_live_tuples(child.oid) AS live_rows
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
WHERE parent.relname = 'events'
ORDER BY child.relname;
```

**Optimal partition count:**
- Too few partitions: each partition is still very large, limited pruning benefit
- Too many partitions: planning overhead increases, open file descriptor pressure
- Rule of thumb: 50-200 partitions is a practical range for most workloads
- Each partition should contain at least 1M rows to justify the overhead

## Common Partitioning Mistakes

1. **Partitioning without filtering on the partition key** -- Queries scan all partitions, worse than a single table
2. **Too many small partitions** -- Planning overhead dominates; thousands of partitions slow the optimizer
3. **Forgetting the DEFAULT partition** -- Inserts with unexpected values fail with an error
4. **Not creating local indexes** -- Partitions without indexes still trigger sequential scans
5. **Using functions on the partition key in WHERE** -- Prevents partition pruning (same as sargability)
6. **Not automating partition creation** -- Missing future partitions cause insert failures at midnight
