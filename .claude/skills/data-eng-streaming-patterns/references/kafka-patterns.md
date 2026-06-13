# Apache Kafka Patterns

Detailed producer/consumer configuration, partitioning strategies, consumer group management, and operational patterns for production Kafka deployments.

## Producer Configuration

### Idempotent Producer

Idempotent producers prevent duplicate messages caused by network retries. The broker deduplicates based on producer ID and sequence number.

```python
from confluent_kafka import Producer

producer = Producer({
    "bootstrap.servers": "broker1:9092,broker2:9092,broker3:9092",

    # Idempotence -- prevents duplicates from retries
    "enable.idempotence": True,
    "acks": "all",                                  # required for idempotence
    "max.in.flight.requests.per.connection": 5,      # safe with idempotence

    # Batching for throughput
    "linger.ms": 20,                                 # wait up to 20ms to batch
    "batch.size": 131072,                            # 128KB batch size
    "compression.type": "lz4",                       # low-latency compression

    # Reliability
    "retries": 2147483647,                           # infinite retries
    "delivery.timeout.ms": 120000,                   # 2 min total timeout
    "request.timeout.ms": 30000,                     # 30s per request

    # Memory management
    "buffer.memory": 67108864,                       # 64MB send buffer
    "max.block.ms": 60000,                           # block 60s when buffer full
})
```

### Transactional Producer

Transactions enable atomic writes across multiple topics and partitions, essential for consume-transform-produce pipelines.

```python
from confluent_kafka import Producer

transactional_producer = Producer({
    "bootstrap.servers": "broker1:9092",
    "transactional.id": "enrichment-pipeline-instance-01",
    "enable.idempotence": True,
    "acks": "all",
    "max.in.flight.requests.per.connection": 5,
})

transactional_producer.init_transactions()

def consume_transform_produce(consumer, input_records):
    """Atomic read-process-write cycle."""
    transactional_producer.begin_transaction()
    try:
        for record in input_records:
            enriched = enrich_transaction(record.value())
            transactional_producer.produce(
                "enriched-transactions",
                key=record.key(),
                value=enriched,
            )
        # Commit offsets and produced messages atomically
        transactional_producer.send_offsets_to_transaction(
            consumer.position(consumer.assignment()),
            consumer.consumer_group_metadata(),
        )
        transactional_producer.commit_transaction()
    except Exception:
        transactional_producer.abort_transaction()
        raise
```

## Partitioning Strategies

### Key-Based Partitioning

Messages with the same key always go to the same partition, guaranteeing per-key ordering.

```python
import hashlib
import struct

def custom_partitioner(key: bytes, num_partitions: int) -> int:
    """Murmur2-compatible partitioning (matches Kafka default)."""
    if key is None:
        return hash(os.urandom(4)) % num_partitions
    h = hashlib.md5(key).digest()
    return struct.unpack(">I", h[:4])[0] % num_partitions

# Partition by user_id -- all events for a user go to same partition
producer.produce(
    topic="user-activity",
    key=f"user-{user_id}".encode("utf-8"),
    value=json.dumps(event).encode("utf-8"),
)
```

### Handling Hot Partitions

When some keys have vastly more traffic, append a random suffix to spread load while maintaining bounded ordering.

```python
import random

def produce_with_spread(producer, topic: str, entity_id: str, event: dict,
                        spread_factor: int = 10):
    """Spread hot keys across multiple partitions.

    Events for the same entity_id may land on different partitions,
    so per-entity ordering is lost. Use only when ordering is not required
    or when downstream handles reordering.
    """
    suffix = random.randint(0, spread_factor - 1)
    partition_key = f"{entity_id}-{suffix}"
    producer.produce(
        topic=topic,
        key=partition_key.encode("utf-8"),
        value=json.dumps(event).encode("utf-8"),
    )
```

### Time-Based Partitioning

Partition by time bucket for time-series workloads where consumers process specific time ranges.

```python
from datetime import datetime

def time_partition_key(event_time: datetime, entity_id: str,
                       bucket_minutes: int = 60) -> str:
    """Partition key combining time bucket and entity for locality."""
    bucket = event_time.strftime("%Y%m%d%H")
    bucket_num = (event_time.minute // bucket_minutes)
    return f"{bucket}-{bucket_num}-{entity_id}"
```

## Consumer Group Patterns

### Basic Consumer with Manual Commit

```python
from confluent_kafka import Consumer, KafkaError

consumer = Consumer({
    "bootstrap.servers": "broker1:9092",
    "group.id": "clickstream-analytics",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,            # manual commit for reliability
    "max.poll.interval.ms": 300000,         # 5 min max processing time
    "session.timeout.ms": 45000,            # 45s heartbeat timeout
    "heartbeat.interval.ms": 15000,         # heartbeat every 15s
    "fetch.min.bytes": 1024,                # wait for 1KB before fetch
    "fetch.max.wait.ms": 500,               # max wait 500ms for fetch
    "max.partition.fetch.bytes": 1048576,   # 1MB per partition per fetch
})

consumer.subscribe(["clickstream-events"])

try:
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            raise Exception(msg.error())

        process_click_event(msg.value())
        consumer.commit(message=msg, asynchronous=False)
finally:
    consumer.close()  # triggers group rebalance
```

### Batch Consumer with Periodic Commit

```python
def consume_in_batches(consumer, batch_size: int = 500,
                       commit_interval_sec: float = 5.0):
    """Consume in batches for throughput, commit periodically."""
    batch = []
    last_commit = time.time()

    while True:
        msg = consumer.poll(timeout=0.1)
        if msg and not msg.error():
            batch.append(msg)

        should_flush = (
            len(batch) >= batch_size
            or (time.time() - last_commit) >= commit_interval_sec
        )

        if batch and should_flush:
            process_batch(batch)
            consumer.commit(asynchronous=False)
            batch.clear()
            last_commit = time.time()
```

## Rebalancing Strategies

### Cooperative Sticky Rebalancing

Cooperative rebalancing avoids stop-the-world pauses by only reassigning partitions that need to move.

```python
consumer = Consumer({
    "bootstrap.servers": "broker1:9092",
    "group.id": "order-processor",
    "partition.assignment.strategy": "cooperative-sticky",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})

def on_revoke(consumer, partitions):
    """Flush in-progress work before partitions are revoked."""
    logger.info(f"Partitions revoked: {[p.partition for p in partitions]}")
    flush_pending_writes()
    consumer.commit(asynchronous=False)

def on_assign(consumer, partitions):
    """Initialize state for newly assigned partitions."""
    logger.info(f"Partitions assigned: {[p.partition for p in partitions]}")
    for p in partitions:
        initialize_partition_state(p.partition)

consumer.subscribe(
    ["orders"],
    on_assign=on_assign,
    on_revoke=on_revoke,
)
```

### Static Group Membership

Static membership avoids unnecessary rebalances during rolling deployments by assigning a persistent identity to each consumer.

```python
import os

consumer = Consumer({
    "bootstrap.servers": "broker1:9092",
    "group.id": "inventory-updater",
    "group.instance.id": f"inventory-{os.environ['HOSTNAME']}",
    "session.timeout.ms": 300000,   # 5 min -- tolerate rolling restarts
    "partition.assignment.strategy": "cooperative-sticky",
})
```

## Topic Configuration for Common Workloads

```python
from confluent_kafka.admin import AdminClient, NewTopic

admin = AdminClient({"bootstrap.servers": "broker1:9092"})

topics = [
    # High-throughput clickstream -- 7 day retention, compacted
    NewTopic("clickstream-events", num_partitions=48, replication_factor=3,
             config={
                 "retention.ms": str(7 * 24 * 3600 * 1000),
                 "compression.type": "lz4",
                 "min.insync.replicas": "2",
                 "segment.bytes": str(256 * 1024 * 1024),     # 256MB segments
             }),

    # Order events -- compacted log, keep latest per key forever
    NewTopic("order-state", num_partitions=24, replication_factor=3,
             config={
                 "cleanup.policy": "compact",
                 "min.compaction.lag.ms": str(3600 * 1000),    # 1 hour lag
                 "min.insync.replicas": "2",
                 "max.message.bytes": str(10 * 1024 * 1024),   # 10MB max
             }),

    # Dead letter queue -- long retention for investigation
    NewTopic("orders-dlq", num_partitions=6, replication_factor=3,
             config={
                 "retention.ms": str(30 * 24 * 3600 * 1000),  # 30 days
                 "min.insync.replicas": "2",
             }),
]

admin.create_topics(topics)
```

## Edge Cases

- **Partition count changes**: Adding partitions changes key-to-partition mapping. Messages with the same key may land on a different partition. Plan partition count for expected peak from the start.
- **Consumer lag during rebalance**: During a rebalance, no consumer in the group processes messages. Use cooperative-sticky to minimize the stop-the-world window.
- **Broker failure with acks=all**: If a broker in the ISR set fails, producers block until `delivery.timeout.ms` expires. Set `min.insync.replicas=2` with replication factor 3 so one broker failure does not block writes.
- **Message ordering with retries**: Without idempotence, retries can reorder messages. Always enable idempotence (`enable.idempotence=True`) when ordering matters.
- **Large messages**: Messages over 1MB require increasing `max.request.size` on producers and `max.message.bytes` on the topic. Consider chunking or external storage references instead.
