# Message Queue Patterns

Detailed patterns for dead letter queues, retry strategies, backpressure management, and circuit breakers in streaming systems.

## Dead Letter Queue (DLQ) Patterns

### Structured DLQ with Metadata

```python
import traceback
from datetime import datetime
from confluent_kafka import Producer

class DLQProducer:
    """Publish failed messages to a dead letter queue with diagnostic metadata."""

    def __init__(self, producer: Producer, dlq_topic: str):
        self.producer = producer
        self.dlq_topic = dlq_topic

    def send_to_dlq(self, original_msg, error: Exception, processing_stage: str):
        dlq_headers = {
            "x-original-topic": original_msg.topic(),
            "x-original-partition": str(original_msg.partition()),
            "x-original-offset": str(original_msg.offset()),
            "x-failure-reason": str(error)[:500],
            "x-failure-type": type(error).__name__,
            "x-failure-stage": processing_stage,
            "x-failed-at": datetime.utcnow().isoformat(),
            "x-stack-trace": traceback.format_exc()[:2000],
        }
        self.producer.produce(
            self.dlq_topic, key=original_msg.key(), value=original_msg.value(),
            headers=[(k, v.encode("utf-8")) for k, v in dlq_headers.items()])
        self.producer.flush()
```

### DLQ Reprocessing Worker

```python
class DLQReprocessor:
    """Reprocess messages from a dead letter queue back to original topics."""

    def __init__(self, consumer, producer, dlq_topic: str,
                 max_reprocess_age_hours: int = 72):
        self.consumer = consumer
        self.producer = producer
        self.dlq_topic = dlq_topic
        self.max_age = max_reprocess_age_hours * 3600

    def reprocess_batch(self, batch_size: int = 100) -> dict:
        stats = {"reprocessed": 0, "expired": 0, "failed_again": 0}
        self.consumer.subscribe([self.dlq_topic])

        for _ in range(batch_size):
            msg = self.consumer.poll(timeout=5.0)
            if msg is None:
                break
            headers = dict(msg.headers() or [])
            original_topic = headers.get("x-original-topic", b"").decode("utf-8")
            try:
                self.producer.produce(original_topic, key=msg.key(),
                    value=msg.value(), headers={"x-reprocessed": "true"})
                self.producer.flush()
                stats["reprocessed"] += 1
            except Exception:
                stats["failed_again"] += 1
            self.consumer.commit(message=msg)
        return stats
```

## Retry Strategies

### Exponential Backoff with Jitter

```python
import random, time

class RetryHandler:
    """Configurable retry with exponential backoff and jitter."""

    def __init__(self, max_retries: int = 5, base_delay: float = 1.0,
                 max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def execute_with_retry(self, func, *args, **kwargs):
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except RetryableError as e:
                last_error = e
                if attempt == self.max_retries:
                    break
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                delay *= (0.5 + random.random() * 0.5)  # jitter
                time.sleep(delay)
            except NonRetryableError:
                raise
        raise MaxRetriesExceededError(
            f"Failed after {self.max_retries} retries") from last_error
```

### Retry Topic Pattern (Kafka)

Publish to delay-specific retry topics instead of sleeping in the consumer.

```python
class RetryTopicConsumer:
    """Multi-level retry using dedicated retry topics."""

    RETRY_DELAYS = {
        "orders.retry-1": 30,       # 30 seconds
        "orders.retry-2": 300,      # 5 minutes
        "orders.retry-3": 3600,     # 1 hour
    }

    def __init__(self, producer, dlq_topic: str = "orders.dlq"):
        self.producer = producer
        self.dlq_topic = dlq_topic
        self.retry_chain = list(self.RETRY_DELAYS.keys())

    def handle_failure(self, msg, error: Exception):
        headers = dict(msg.headers() or [])
        current_retry = headers.get("x-retry-topic", b"").decode("utf-8")
        if not current_retry:
            next_topic = self.retry_chain[0]
        else:
            try:
                next_topic = self.retry_chain[self.retry_chain.index(current_retry) + 1]
            except (ValueError, IndexError):
                self.producer.produce(self.dlq_topic, key=msg.key(),
                    value=msg.value(), headers={"x-failure-reason": str(error)[:500]})
                return
        self.producer.produce(next_topic, key=msg.key(), value=msg.value(),
            headers={"x-retry-topic": next_topic, "x-original-topic": msg.topic()})
```

## Backpressure Strategies

### Consumer Pause/Resume

```python
from confluent_kafka import Consumer, TopicPartition

class BackpressureConsumer:
    """Consumer that pauses when downstream cannot keep up."""

    def __init__(self, consumer: Consumer, max_buffer_size: int = 10000):
        self.consumer = consumer
        self.max_buffer_size = max_buffer_size
        self.buffer = []
        self.paused_partitions = set()

    def poll_with_backpressure(self):
        if len(self.buffer) >= self.max_buffer_size:
            self._pause_all()
        elif len(self.buffer) < self.max_buffer_size * 0.5:
            self._resume_all()
        msg = self.consumer.poll(timeout=0.1)
        if msg and not msg.error():
            self.buffer.append(msg)
        batch = self.buffer[:100]
        self.buffer = self.buffer[100:]
        return batch

    def _pause_all(self):
        assigned = self.consumer.assignment()
        to_pause = [tp for tp in assigned
                    if (tp.topic, tp.partition) not in self.paused_partitions]
        if to_pause:
            self.consumer.pause(to_pause)
            self.paused_partitions.update((tp.topic, tp.partition) for tp in to_pause)

    def _resume_all(self):
        if self.paused_partitions:
            self.consumer.resume([TopicPartition(t, p) for t, p in self.paused_partitions])
            self.paused_partitions.clear()
```

## Circuit Breaker Pattern

Prevent cascading failures when a downstream service is unhealthy.

```python
import time
from enum import Enum
from threading import Lock

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5,
                 recovery_timeout: float = 30.0,
                 half_open_max_calls: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.lock = Lock()

    def call(self, func, *args, **kwargs):
        with self.lock:
            if self.state == CircuitState.OPEN:
                if (time.monotonic() - self.last_failure_time) >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise CircuitOpenError("Circuit open")
        try:
            result = func(*args, **kwargs)
            with self.lock:
                self.failure_count = 0
                if self.state == CircuitState.HALF_OPEN:
                    self.state = CircuitState.CLOSED
            return result
        except Exception:
            with self.lock:
                self.failure_count += 1
                self.last_failure_time = time.monotonic()
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
            raise
```

### Using Circuit Breaker in a Stream Processor

```python
class EnrichmentProcessor:
    def __init__(self):
        self.circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        self.dlq = DLQProducer(producer, "enrichment-dlq")

    def process(self, msg):
        try:
            enriched = self.circuit.call(self._call_enrichment_api, msg.value())
            produce_enriched(enriched)
        except CircuitOpenError:
            self.dlq.send_to_dlq(msg, CircuitOpenError(), "enrichment")
        except Exception as e:
            self.dlq.send_to_dlq(msg, e, "enrichment")

    def _call_enrichment_api(self, payload):
        resp = requests.post("http://enrichment-service/enrich",
                             json=payload, timeout=5)
        resp.raise_for_status()
        return resp.json()
```

## Monitoring Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

messages_processed = Counter("stream_messages_processed_total",
    "Total messages processed", ["topic", "consumer_group"])
processing_latency = Histogram("stream_processing_latency_seconds",
    "Processing latency", ["topic"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0])
consumer_lag = Gauge("stream_consumer_lag",
    "Consumer group lag", ["topic", "partition", "group"])
dlq_messages = Counter("stream_dlq_messages_total",
    "Messages sent to DLQ", ["topic", "failure_reason"])
```

## Edge Cases

- **DLQ ordering**: Messages in DLQ are not ordered like the original topic. Sort by original offset or timestamp before replaying if order matters.
- **Retry storms**: Many simultaneous failures amplify load via retry topics. Use jittered delays and rate-limit the retry consumer.
- **Circuit breaker granularity**: A single breaker per service may be too coarse. Consider per-endpoint or per-partition breakers.
- **Backpressure propagation**: Pausing a consumer increases lag but does not signal upstream producers. Combine consumer pause with producer rate limiting for end-to-end backpressure.
- **DLQ consumer group conflicts**: Use a dedicated consumer group for DLQ reprocessing to avoid offset conflicts with the main consumer.
