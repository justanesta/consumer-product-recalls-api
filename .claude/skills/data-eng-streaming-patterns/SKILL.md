---
name: data-eng-streaming-patterns
description: |
  Streaming data patterns for event-driven architectures and real-time processing.
  Use this skill when building Kafka pipelines, implementing CDC, designing event
  sourcing systems, or working with stream processing frameworks like Flink and
  Kafka Streams. Covers delivery guarantees, backpressure, dead letter queues,
  and production-grade streaming infrastructure.
---

# Streaming Data Patterns

Real-time data processing patterns for event-driven systems and streaming pipelines.

## Core Principles

1. **Events are immutable facts** -- Never mutate events in-flight; produce corrective events instead.
2. **Design for failure and replay** -- Every component must handle reprocessing gracefully through idempotent writes and offset management.
3. **Exactly-once is a system property** -- It emerges from idempotent producers, transactional writes, and deterministic processing combined.
4. **Backpressure over data loss** -- When consumers fall behind, slow down producers or buffer intelligently rather than dropping messages.
5. **Schema evolution is mandatory** -- Plan for backward and forward compatible schema changes from day one using a schema registry.

## Apache Kafka Fundamentals

Kafka organizes data into topics split into partitions. Producers write by key for ordering; consumers read in groups for load balancing.

```python
from confluent_kafka import Producer
import json

producer = Producer({
    "bootstrap.servers": "broker1:9092,broker2:9092",
    "enable.idempotence": True,
    "acks": "all",
    "compression.type": "lz4",
})

def produce_clickstream_event(user_id: str, event: dict):
    """Partition by user_id to preserve per-user ordering."""
    producer.produce(
        topic="clickstream-events",
        key=user_id.encode("utf-8"),
        value=json.dumps(event).encode("utf-8"),
        callback=lambda err, msg: logger.error(f"Failed: {err}") if err else None,
    )
    producer.poll(0)
```

See [kafka-patterns.md](references/kafka-patterns.md) for:
- Consumer group configuration and rebalancing strategies
- Partitioning strategies for high-cardinality keys
- Exactly-once producer transactions
- Topic configuration and retention policies

## Change Data Capture (CDC) Patterns

CDC captures row-level changes from database transaction logs, avoiding polling overhead.

```yaml
# Debezium PostgreSQL connector
name: "orders-connector"
config:
  connector.class: "io.debezium.connector.postgresql.PostgresConnector"
  database.hostname: "postgres-primary"
  database.dbname: "inventory"
  table.include.list: "public.orders,public.customers"
  plugin.name: "pgoutput"
  slot.name: "debezium_slot"
  tombstones.on.delete: true
  snapshot.mode: "initial"
  transforms: "route"
  transforms.route.type: "org.apache.kafka.connect.transforms.RegexRouter"
  transforms.route.regex: "([^.]+)\\.([^.]+)\\.([^.]+)"
  transforms.route.replacement: "cdc.$3"
```

See [cdc-patterns.md](references/cdc-patterns.md) for:
- Outbox pattern for reliable event publishing
- Log-based vs trigger-based CDC trade-offs
- Handling schema migrations during CDC
- Snapshot strategies for initial data load

## Event-Driven Architecture

Event sourcing stores state as a sequence of events. CQRS separates write and read models for independent scaling.

```python
from dataclasses import dataclass, field
from typing import List
import uuid

@dataclass(frozen=True)
class FundsDeposited:
    account_id: str = ""
    amount: float = 0.0
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

class BankAccount:
    """Event-sourced aggregate -- all state derived from events."""
    def __init__(self, account_id: str):
        self.account_id = account_id
        self.balance = 0.0
        self._pending_events: List = []

    def apply(self, event):
        if isinstance(event, FundsDeposited):
            self.balance += event.amount

    def deposit(self, amount: float):
        event = FundsDeposited(account_id=self.account_id, amount=amount)
        self.apply(event)
        self._pending_events.append(event)
```

See [event-sourcing-patterns.md](references/event-sourcing-patterns.md) for:
- Event store implementation with snapshots
- Projection rebuilding and versioning
- CQRS read model synchronization

## Exactly-Once Semantics and Delivery Guarantees

Exactly-once requires coordination across producer, broker, and consumer via Kafka transactions.

```java
// Kafka transactional producer -- atomic read-process-write
producer.initTransactions();
try {
    producer.beginTransaction();
    ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(100));
    for (ConsumerRecord<String, String> record : records) {
        String enriched = enrichClickEvent(record.value());
        producer.send(new ProducerRecord<>("enriched-clicks", record.key(), enriched));
    }
    // Commit offsets and produced records atomically
    producer.sendOffsetsToTransaction(currentOffsets(records), consumerGroupMetadata);
    producer.commitTransaction();
} catch (ProducerFencedException e) {
    producer.close();
} catch (KafkaException e) {
    producer.abortTransaction();
}
```

See [delivery-guarantees.md](references/delivery-guarantees.md) for:
- At-least-once vs at-most-once design trade-offs
- Idempotency keys and deduplication windows
- Consumer offset management strategies
- End-to-end exactly-once with Flink checkpoints

## Stream Processing

Windowing groups unbounded streams into finite chunks for aggregation. Watermarks track event-time progress.

```python
# PyFlink -- tumbling window aggregation for IoT sensors
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common.time import Time
from pyflink.datastream.functions import AggregateFunction

class TemperatureAggregator(AggregateFunction):
    def create_accumulator(self):
        return {"sum": 0.0, "count": 0, "max": float("-inf")}
    def add(self, value, acc):
        acc["sum"] += value.temperature
        acc["count"] += 1
        acc["max"] = max(acc["max"], value.temperature)
        return acc
    def get_result(self, acc):
        return {"avg": acc["sum"] / acc["count"], "max": acc["max"]}
    def merge(self, a, b):
        return {"sum": a["sum"] + b["sum"], "count": a["count"] + b["count"],
                "max": max(a["max"], b["max"])}

sensor_stream \
    .key_by(lambda e: e.sensor_id) \
    .window(TumblingEventTimeWindows.of(Time.minutes(5))) \
    .aggregate(TemperatureAggregator()) \
    .add_sink(alert_sink)
```

See [stream-processing-patterns.md](references/stream-processing-patterns.md) for:
- Sliding and session window patterns
- Watermark strategies for late-arriving data
- State backends and checkpointing
- Stream-table joins and enrichment

## Message Queue Patterns

Dead letter queues capture messages that fail after exhausting retries. Backpressure prevents downstream overload.

```python
class ResilientConsumer:
    """Consumer with exponential backoff retry and dead letter queue."""
    def __init__(self, source_topic: str, dlq_topic: str, max_retries: int = 3):
        self.consumer = Consumer({"bootstrap.servers": "broker1:9092",
            "group.id": "payment-processor", "enable.auto.commit": False})
        self.producer = Producer({"bootstrap.servers": "broker1:9092"})
        self.source_topic = source_topic
        self.dlq_topic = dlq_topic
        self.max_retries = max_retries

    def process_with_retry(self, msg):
        retry_count = int(msg.headers().get("x-retry-count", b"0"))
        try:
            process_payment(msg.value())
            self.consumer.commit(msg)
        except TransientError:
            if retry_count < self.max_retries:
                time.sleep(min(2 ** retry_count, 60))
                self.producer.produce(self.source_topic, value=msg.value(),
                    headers={"x-retry-count": str(retry_count + 1)})
            else:
                self.send_to_dlq(msg, "max_retries_exceeded")
        except PoisonPillError as e:
            self.send_to_dlq(msg, str(e))
```

See [message-queue-patterns.md](references/message-queue-patterns.md) for:
- Circuit breaker implementation for downstream services
- Backpressure strategies (rate limiting, consumer pause/resume)
- Priority queues and message ordering
- DLQ monitoring and reprocessing workflows

## Anti-Patterns

| Avoid | Use Instead |
|-------|-------------|
| Auto-commit offsets with side effects | Manual commit after processing completes |
| Single partition topics for high throughput | Partition by key with sufficient partition count |
| Polling databases for change detection | Log-based CDC with Debezium |
| Unbounded state in stream processors | Windowed aggregations with TTL-based state expiry |
| Synchronous HTTP calls in hot path | Async event publication with consumer processing |
| No schema registry for Avro/Protobuf | Schema registry with compatibility checks enforced |
| Retry forever on poison pill messages | Dead letter queue after bounded retries |
| Processing-time windows for event data | Event-time windows with watermark strategies |
| Giant monolith consumer groups | Small focused consumer groups per use case |
| Ignoring consumer lag metrics | Alerting on lag with auto-scaling consumers |

## Performance

- **Batching**: Configure `linger.ms` (5-100ms) and `batch.size` (64KB-1MB) on producers to amortize network overhead
- **Compression**: Use LZ4 for low-latency or ZSTD for high-compression at the producer
- **Partition count**: Target 10-50 MB/s per partition; start with `max(throughput_mb / 10, consumer_count)`
- **Consumer parallelism**: One consumer thread per partition; scale instances up to the partition count
- **State backend**: Use RocksDB for Flink state exceeding memory; enable incremental checkpoints
- **Serialization**: Prefer Avro or Protobuf over JSON for 2-5x smaller payloads with schema enforcement
- **Network tuning**: Set `fetch.min.bytes` and `fetch.max.wait.ms` to batch consumer fetches
- **Replication**: Use 3 replicas with `min.insync.replicas=2` for durability

source: Apache Kafka docs, Confluent Platform docs, Apache Flink docs, Debezium docs, Martin Kleppmann - Designing Data-Intensive Applications
