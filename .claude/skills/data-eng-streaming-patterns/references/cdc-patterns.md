# Change Data Capture (CDC) Patterns

Detailed patterns for capturing database changes and streaming them as events, including Debezium configuration, the transactional outbox pattern, and trade-offs between CDC approaches.

## Log-Based CDC with Debezium

### PostgreSQL Connector -- Full Configuration

```yaml
name: "orders-cdc-connector"
config:
  connector.class: "io.debezium.connector.postgresql.PostgresConnector"
  database.hostname: "postgres-primary.internal"
  database.port: "5432"
  database.user: "debezium_replication"
  database.password: "${file:/secrets/debezium-password}"
  database.dbname: "ecommerce"
  database.server.name: "ecommerce-db"

  # Table selection
  schema.include.list: "public"
  table.include.list: "public.orders,public.order_items,public.customers"
  column.exclude.list: "public.customers.ssn,public.customers.credit_card"

  # Replication slot configuration
  plugin.name: "pgoutput"
  slot.name: "debezium_orders"
  publication.name: "dbz_orders_pub"
  publication.autocreate.mode: "filtered"

  # Snapshot configuration
  snapshot.mode: "initial"
  snapshot.lock.timeout.ms: "10000"

  # Topic routing
  topic.prefix: "cdc"
  topic.creation.default.replication.factor: 3
  topic.creation.default.partitions: 12

  # Heartbeat to prevent WAL buildup during low-traffic periods
  heartbeat.interval.ms: "30000"
  heartbeat.action.query: "UPDATE debezium_heartbeat SET last_heartbeat = NOW()"

  # Tombstone events for deletes (enables log compaction)
  tombstones.on.delete: true

  # Schema history
  schema.history.internal.kafka.bootstrap.servers: "broker1:9092"
  schema.history.internal.kafka.topic: "schema-changes.ecommerce"
```

### MySQL Connector

```yaml
name: "inventory-cdc-connector"
config:
  connector.class: "io.debezium.connector.mysql.MySqlConnector"
  database.hostname: "mysql-primary.internal"
  database.port: "3306"
  database.user: "debezium"
  database.password: "${file:/secrets/debezium-password}"
  database.server.id: "184054"
  database.server.name: "inventory-db"
  database.include.list: "inventory"
  table.include.list: "inventory.products,inventory.stock_levels"

  # Use GTID for position tracking
  include.schema.changes: true
  gtid.source.includes: ""

  # Binlog configuration
  database.history.kafka.bootstrap.servers: "broker1:9092"
  database.history.kafka.topic: "schema-history.inventory"
  binlog.buffer.size: 0

  snapshot.mode: "when_needed"
```

## The Transactional Outbox Pattern

The outbox pattern solves the dual-write problem: you need to update a database AND publish an event, but you cannot do both atomically. Instead, write the event to an outbox table within the same database transaction, then use CDC to stream outbox rows to Kafka.

### Database Schema

```sql
-- Outbox table: events written in same transaction as business data
CREATE TABLE outbox_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  VARCHAR(255) NOT NULL,
    aggregate_id    VARCHAR(255) NOT NULL,
    event_type      VARCHAR(255) NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published       BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_outbox_unpublished ON outbox_events (created_at)
    WHERE published = FALSE;
```

### Application Code

```python
from sqlalchemy.orm import Session
import json
import uuid

def place_order(session: Session, order_data: dict):
    """Business logic and event in same transaction."""
    order = Order(
        id=str(uuid.uuid4()),
        customer_id=order_data["customer_id"],
        total=order_data["total"],
        status="placed",
    )
    session.add(order)

    # Write event to outbox in SAME transaction
    outbox_event = OutboxEvent(
        aggregate_type="Order",
        aggregate_id=order.id,
        event_type="OrderPlaced",
        payload=json.dumps({
            "order_id": order.id,
            "customer_id": order_data["customer_id"],
            "total": float(order_data["total"]),
            "items": order_data["items"],
        }),
    )
    session.add(outbox_event)
    session.commit()  # both or neither
```

### Debezium Outbox Connector Config

```yaml
name: "outbox-connector"
config:
  connector.class: "io.debezium.connector.postgresql.PostgresConnector"
  database.hostname: "postgres-primary.internal"
  database.dbname: "ecommerce"
  database.user: "debezium_replication"
  table.include.list: "public.outbox_events"

  # Outbox event router -- transforms outbox rows into proper events
  transforms: "outbox"
  transforms.outbox.type: "io.debezium.transforms.outbox.EventRouter"
  transforms.outbox.table.fields.additional.placement: "event_type:header:eventType"
  transforms.outbox.route.by.field: "aggregate_type"
  transforms.outbox.route.topic.replacement: "events.${routedByValue}"

  # Delete processed outbox rows (optional -- keeps table small)
  transforms.outbox.table.expand.json.payload: true
```

## Trigger-Based CDC

When log-based CDC is not available (legacy databases, restricted access), trigger-based CDC captures changes via database triggers.

```sql
-- Change tracking table
CREATE TABLE change_log (
    id          BIGSERIAL PRIMARY KEY,
    table_name  VARCHAR(255) NOT NULL,
    operation   VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    record_key  VARCHAR(255) NOT NULL,
    old_data    JSONB,
    new_data    JSONB,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published   BOOLEAN NOT NULL DEFAULT FALSE
);

-- Trigger function
CREATE OR REPLACE FUNCTION capture_changes()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO change_log (table_name, operation, record_key, old_data, new_data)
    VALUES (
        TG_TABLE_NAME,
        TG_OP,
        COALESCE(NEW.id::TEXT, OLD.id::TEXT),
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE')
             THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE')
             THEN to_jsonb(NEW) END
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Attach to tables
CREATE TRIGGER orders_cdc_trigger
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION capture_changes();
```

### Polling the Change Log

```python
import time
from datetime import datetime

class TriggerBasedCDCPublisher:
    """Poll change_log and publish to Kafka."""

    def __init__(self, db_session, producer, poll_interval: float = 1.0):
        self.session = db_session
        self.producer = producer
        self.poll_interval = poll_interval

    def run(self):
        while True:
            changes = self.session.execute(
                """SELECT id, table_name, operation, record_key,
                          old_data, new_data, changed_at
                   FROM change_log
                   WHERE published = FALSE
                   ORDER BY id
                   LIMIT 1000"""
            ).fetchall()

            for change in changes:
                topic = f"cdc.{change.table_name}"
                event = {
                    "op": change.operation.lower()[0],  # c, u, d
                    "before": change.old_data,
                    "after": change.new_data,
                    "ts_ms": int(change.changed_at.timestamp() * 1000),
                    "source": {"table": change.table_name},
                }
                self.producer.produce(
                    topic, key=change.record_key, value=json.dumps(event)
                )

            if changes:
                ids = [c.id for c in changes]
                self.session.execute(
                    "UPDATE change_log SET published = TRUE WHERE id = ANY(:ids)",
                    {"ids": ids},
                )
                self.session.commit()
                self.producer.flush()

            time.sleep(self.poll_interval)
```

## CDC Approach Comparison

| Factor | Log-Based (Debezium) | Trigger-Based | Outbox Pattern |
|--------|---------------------|---------------|----------------|
| Performance impact | Minimal -- reads WAL | Moderate -- trigger overhead per row | Minimal -- extra INSERT per transaction |
| Captures deletes | Yes (tombstones) | Yes (trigger on DELETE) | Only if explicitly written |
| Schema changes | Automatic detection | Requires trigger updates | Application controls payload |
| Ordering guarantee | WAL order (total order) | Sequence from change_log ID | Outbox ID ordering |
| Operational complexity | Requires replication slot | Simpler setup | Requires CDC on outbox table |
| Best for | General purpose CDC | Legacy databases | Domain event publishing |

## Handling Schema Migrations During CDC

Schema changes can break CDC pipelines. Follow these practices:

```sql
-- SAFE: Adding a nullable column (backward compatible)
ALTER TABLE orders ADD COLUMN gift_message TEXT;

-- SAFE: Adding a column with a default
ALTER TABLE orders ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;

-- DANGEROUS: Renaming a column breaks downstream consumers
-- Instead, add new column, migrate data, deprecate old column
ALTER TABLE orders ADD COLUMN recipient_name TEXT;
UPDATE orders SET recipient_name = customer_name;
-- Later, after all consumers migrate:
-- ALTER TABLE orders DROP COLUMN customer_name;

-- DANGEROUS: Changing column type
-- Instead, add new column with new type
ALTER TABLE orders ADD COLUMN total_cents BIGINT;
UPDATE orders SET total_cents = (total * 100)::BIGINT;
```

## Edge Cases

- **WAL retention**: If Debezium falls behind, PostgreSQL may remove WAL segments the connector has not read. Configure `wal_keep_size` or use replication slots with monitoring on `pg_replication_slots`.
- **Large transactions**: A single transaction updating millions of rows produces millions of CDC events simultaneously. Use `max.batch.size` on the connector to throttle output.
- **Snapshot consistency**: The initial snapshot reads the current table state. Events arriving during the snapshot may be duplicated. Debezium handles this with watermarking, but downstream must still handle duplicates.
- **Connector restart after long downtime**: If the replication slot was dropped, Debezium must re-snapshot. Use `snapshot.mode=when_needed` to handle this automatically.
- **Timezone handling**: CDC timestamps follow the database timezone. Normalize to UTC in the CDC event transform to avoid downstream confusion.
