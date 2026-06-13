# Delivery Guarantees

Detailed patterns for at-least-once, at-most-once, and exactly-once message delivery, idempotency strategies, and offset management for streaming systems.

## Delivery Semantics Overview

| Guarantee | Producer Config | Consumer Config | Data Risk | Use Case |
|-----------|----------------|-----------------|-----------|----------|
| At-most-once | `acks=0` or `acks=1` | Auto-commit before processing | Message loss | Metrics, non-critical logs |
| At-least-once | `acks=all`, idempotent | Manual commit after processing | Duplicates | Most workloads (with idempotent sink) |
| Exactly-once | Transactional producer | `isolation.level=read_committed` | None (if done correctly) | Financial transactions, billing |

## At-Most-Once Delivery

Offsets are committed before processing. A crash loses the message.

```python
consumer = Consumer({
    "bootstrap.servers": "broker1:9092",
    "group.id": "metrics-collector",
    "auto.offset.reset": "latest",
    "enable.auto.commit": True,           # commit before processing
    "auto.commit.interval.ms": 1000,
})
consumer.subscribe(["sensor-metrics"])

while True:
    msg = consumer.poll(timeout=1.0)
    if msg is None or msg.error():
        continue
    # If we crash here, the offset is already committed -- message lost
    try:
        record_metric(msg.value())
    except Exception:
        pass  # drop on failure
```

## At-Least-Once Delivery

Offsets committed after processing. A crash between processing and commit causes reprocessing.

```python
consumer = Consumer({
    "bootstrap.servers": "broker1:9092",
    "group.id": "order-processor",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,          # manual commit after processing
})
consumer.subscribe(["orders"])

while True:
    msg = consumer.poll(timeout=1.0)
    if msg is None or msg.error():
        continue
    try:
        process_order(msg.value())        # may produce duplicates on retry
        consumer.commit(message=msg, asynchronous=False)
    except TransientError:
        logger.warning(f"Transient failure, will retry: {msg.offset()}")
    except PermanentError:
        send_to_dlq(msg)
        consumer.commit(message=msg, asynchronous=False)
```

## Exactly-Once with Kafka Transactions

```java
KafkaProducer<String, String> producer = new KafkaProducer<>(producerProps);
producer.initTransactions();

KafkaConsumer<String, String> consumer = new KafkaConsumer<>(consumerProps);
consumer.subscribe(Arrays.asList("raw-payments"));

while (true) {
    ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(200));
    if (records.isEmpty()) continue;

    producer.beginTransaction();
    try {
        for (ConsumerRecord<String, String> record : records) {
            String enriched = enrichPayment(record.value());
            producer.send(new ProducerRecord<>("enriched-payments", record.key(), enriched));
        }
        // Atomic: commit consumer offsets + produced records
        producer.sendOffsetsToTransaction(getOffsets(records), consumer.groupMetadata());
        producer.commitTransaction();
    } catch (ProducerFencedException e) {
        producer.close();
        break;
    } catch (KafkaException e) {
        producer.abortTransaction();
    }
}
```

## Idempotency Patterns

### Database Upsert with Idempotency Key

```python
def process_payment_idempotent(db_session, event: dict):
    """Idempotent payment processing using event_id as dedup key."""
    event_id = event["event_id"]
    existing = db_session.execute(
        "SELECT 1 FROM processed_events WHERE event_id = :eid",
        {"eid": event_id}).fetchone()
    if existing:
        return  # already processed

    db_session.execute(
        """INSERT INTO payments (payment_id, amount, customer_id, status)
           VALUES (:pid, :amount, :cid, 'completed')
           ON CONFLICT (payment_id) DO NOTHING""",
        {"pid": event["payment_id"], "amount": event["amount"],
         "cid": event["customer_id"]})
    db_session.execute(
        "INSERT INTO processed_events (event_id, processed_at) VALUES (:eid, NOW())",
        {"eid": event_id})
    db_session.commit()
```

### Deduplication with Time-Bounded Window

```python
import redis
from datetime import timedelta

class DeduplicationFilter:
    """Deduplicate events using Redis with TTL-based expiry."""

    def __init__(self, redis_client: redis.Redis,
                 window: timedelta = timedelta(hours=24)):
        self.redis = redis_client
        self.window_seconds = int(window.total_seconds())

    def is_duplicate(self, event_id: str) -> bool:
        key = f"dedup:{event_id}"
        is_new = self.redis.set(key, "1", nx=True, ex=self.window_seconds)
        return not is_new

    def process_if_new(self, event: dict, handler):
        if self.is_duplicate(event["event_id"]):
            return None
        return handler(event)
```

### Idempotent HTTP API Calls

```python
import hashlib

def call_payment_gateway_idempotent(payment: dict) -> dict:
    """Make idempotent API call using deterministic idempotency key."""
    key_input = f"{payment['order_id']}:{payment['amount']}:{payment['currency']}"
    idempotency_key = hashlib.sha256(key_input.encode()).hexdigest()
    response = requests.post(
        "https://api.payments.example.com/charges",
        json=payment,
        headers={"Idempotency-Key": idempotency_key},
        timeout=30)
    response.raise_for_status()
    return response.json()
```

## Consumer Offset Management

### Manual Offset Tracking in External Store

Store offsets alongside data in the sink database for atomic commit.

```python
class ExternalOffsetConsumer:
    """Store offsets in the sink database for atomic processing."""

    def __init__(self, consumer, db_session, consumer_group: str):
        self.consumer = consumer
        self.session = db_session
        self.consumer_group = consumer_group

    def initialize_offsets(self):
        stored = self.session.execute(
            "SELECT topic, partition_id, offset_val FROM consumer_offsets "
            "WHERE consumer_group = :group",
            {"group": self.consumer_group}).fetchall()
        for row in stored:
            tp = TopicPartition(row.topic, row.partition_id, row.offset_val + 1)
            self.consumer.seek(tp)

    def process_and_commit(self, messages):
        for msg in messages:
            process_record(self.session, msg.value())
            self.session.execute(
                """INSERT INTO consumer_offsets
                   (consumer_group, topic, partition_id, offset_val)
                   VALUES (:group, :topic, :part, :offset)
                   ON CONFLICT (consumer_group, topic, partition_id)
                   DO UPDATE SET offset_val = :offset""",
                {"group": self.consumer_group, "topic": msg.topic(),
                 "part": msg.partition(), "offset": msg.offset()})
        self.session.commit()  # data + offsets atomically
```

## Choosing the Right Guarantee

```
Is data loss acceptable?
├── Yes --> At-most-once (metrics, ephemeral logs)
└── No
    ├── Can the sink handle duplicates?
    │   ├── Yes --> At-least-once (simplest reliable option)
    │   └── No --> Can you make the sink idempotent?
    │       ├── Yes --> At-least-once + idempotent sink (recommended)
    │       └── No --> Exactly-once transactions (most complex)
    └── Is it Kafka-to-Kafka only?
        ├── Yes --> Kafka transactions
        └── No --> Flink with two-phase commit sinks
```

## Edge Cases

- **Transactional ID conflicts**: Two producer instances with the same `transactional.id` cause fencing. Use instance-specific IDs (include hostname or pod name).
- **Transaction timeout**: Transactions exceeding `transaction.timeout.ms` (default 60s) are aborted by the broker. Tune based on batch size and processing time.
- **Deduplication window expiry**: Duplicates arriving after the window closes will be reprocessed. Size the window based on maximum expected retry delay.
- **Rebalance during transaction**: A rebalance during an open transaction triggers `CommitFailedException`. Abort and retry with newly assigned partitions.
- **Zombie instances**: A fenced producer may still attempt writes. Kafka rejects stale writes via epoch numbers, but the zombie wastes resources until it discovers it has been fenced.
