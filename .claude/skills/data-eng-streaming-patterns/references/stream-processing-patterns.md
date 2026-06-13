# Stream Processing Patterns

Detailed patterns for windowing, watermarks, late data handling, state management, and stream enrichment using Flink and Kafka Streams.

## Windowing Patterns

### Tumbling Windows

Fixed-size, non-overlapping windows. Every event belongs to exactly one window.

```python
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common.time import Time

sensor_stream = env.from_source(kafka_source, watermark_strategy, "iot-sensors")

sensor_stream \
    .key_by(lambda event: event["sensor_id"]) \
    .window(TumblingEventTimeWindows.of(Time.minutes(5))) \
    .reduce(lambda a, b: {
        "sensor_id": a["sensor_id"],
        "temp_sum": a["temp_sum"] + b["temp_sum"],
        "count": a["count"] + b["count"],
        "max_temp": max(a["max_temp"], b["max_temp"]),
    }) \
    .add_sink(alert_sink)
```

### Sliding Windows

Fixed-size windows that overlap. An event may belong to multiple windows.

```python
from pyflink.datastream.window import SlidingEventTimeWindows

# 10-minute window, sliding every 1 minute -- each event appears in 10 windows
clickstream \
    .key_by(lambda e: e["page_id"]) \
    .window(SlidingEventTimeWindows.of(Time.minutes(10), Time.minutes(1))) \
    .aggregate(PageViewAggregator()) \
    .filter(lambda r: r["view_count"] > 1000) \
    .add_sink(trending_pages_sink)
```

### Session Windows

Dynamic windows that close after a gap of inactivity. Natural fit for user sessions.

```python
from pyflink.datastream.window import EventTimeSessionWindows

clickstream \
    .key_by(lambda e: e["user_id"]) \
    .window(EventTimeSessionWindows.with_gap(Time.minutes(30))) \
    .aggregate(SessionAggregator()) \
    .map(lambda s: {
        "user_id": s["user_id"],
        "session_start": s["first_event_time"],
        "session_end": s["last_event_time"],
        "page_views": s["event_count"],
        "duration_seconds": s["duration"],
    }) \
    .add_sink(session_analytics_sink)
```

## Watermark Strategies

Watermarks track event-time progress and tell the system when a window can be closed.

```python
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.common.time import Time

# Allow events to arrive up to 10 seconds late
watermark_strategy = WatermarkStrategy \
    .for_bounded_out_of_orderness(Time.seconds(10)) \
    .with_timestamp_assigner(lambda event, _: event["event_time_ms"])

# For IoT with known network delays, use larger bounds
iot_watermark = WatermarkStrategy \
    .for_bounded_out_of_orderness(Time.minutes(2)) \
    .with_timestamp_assigner(lambda reading, _: reading["sensor_timestamp_ms"])
```

### Custom Watermark Generator

```python
from pyflink.common.watermark_strategy import WatermarkGenerator

class PerPartitionWatermarkGenerator(WatermarkGenerator):
    def __init__(self, max_delay_ms: int = 10000):
        self.max_delay_ms = max_delay_ms
        self.current_max_timestamp = 0

    def on_event(self, event, event_timestamp, output):
        self.current_max_timestamp = max(self.current_max_timestamp, event_timestamp)

    def on_periodic_emit(self, output):
        output.emit_watermark(self.current_max_timestamp - self.max_delay_ms)
```

## Late Data Handling

### Side Output for Late Events

```python
from pyflink.datastream import OutputTag

late_events_tag = OutputTag("late-events")

windowed_stream = sensor_stream \
    .key_by(lambda e: e["sensor_id"]) \
    .window(TumblingEventTimeWindows.of(Time.minutes(5))) \
    .allowed_lateness(Time.minutes(10)) \
    .side_output_late_data(late_events_tag) \
    .aggregate(TemperatureAggregator())

windowed_stream.add_sink(analytics_sink)           # on-time results
late_stream = windowed_stream.get_side_output(late_events_tag)
late_stream.add_sink(late_events_sink)             # late events
```

### Kafka Streams Grace Period

```java
// Accept late data for 2 minutes after window closes
KTable<Windowed<String>, Long> counts = readings
    .groupByKey()
    .windowedBy(TimeWindows.ofSizeAndGrace(
        Duration.ofMinutes(5), Duration.ofMinutes(2)))
    .count();
```

## State Management

### Flink State Backends

```python
# Heap state -- fast, limited by JVM memory
env.set_state_backend(HashMapStateBackend())

# RocksDB -- scales beyond memory, uses local disk
from pyflink.datastream.state_backend import RocksDBStateBackend
env.set_state_backend(RocksDBStateBackend(
    "s3://flink-state/checkpoints/", enable_incremental_checkpoints=True))
```

### State TTL for Bounded Growth

```java
StateTtlConfig ttlConfig = StateTtlConfig
    .newBuilder(org.apache.flink.api.common.time.Time.hours(24))
    .setUpdateType(StateTtlConfig.UpdateType.OnCreateAndWrite)
    .setStateVisibility(StateTtlConfig.StateVisibility.NeverReturnExpired)
    .cleanupFullSnapshot()
    .build();

ValueStateDescriptor<UserSession> descriptor =
    new ValueStateDescriptor<>("user-session", UserSession.class);
descriptor.enableTimeToLive(ttlConfig);
```

## Stream-Table Joins and Enrichment

### Kafka Streams KStream-KTable Join

```java
KStream<String, ClickEvent> clicks = builder.stream("clicks");
KTable<String, UserProfile> users = builder.table("user-profiles");

KStream<String, EnrichedClick> enrichedClicks = clicks.leftJoin(
    users,
    (click, profile) -> new EnrichedClick(
        click.getPageUrl(), click.getTimestamp(),
        profile != null ? profile.getSegment() : "unknown",
        profile != null ? profile.getRegion() : "unknown"));

enrichedClicks.to("enriched-clicks");
```

### Async Enrichment with External Service

```python
from pyflink.datastream.functions import AsyncFunction
from pyflink.datastream import AsyncDataStream
import aiohttp

class AsyncGeoEnricher(AsyncFunction):
    def open(self, runtime_context):
        self.session = aiohttp.ClientSession()

    async def async_invoke(self, event, result_future):
        try:
            async with self.session.get(
                f"http://geo-service/lookup/{event['ip_address']}",
                timeout=aiohttp.ClientTimeout(total=5)) as resp:
                geo = await resp.json()
                event["country"] = geo.get("country", "unknown")
        except Exception:
            event["country"] = "unknown"
        result_future.complete(event)

enriched = AsyncDataStream.unordered_wait(
    sensor_stream, AsyncGeoEnricher(), timeout=100, capacity=1000)
```

## Checkpointing and Fault Tolerance

```python
from pyflink.datastream.checkpointing_mode import CheckpointingMode

env.enable_checkpointing(60000)
config = env.get_checkpoint_config()
config.set_checkpointing_mode(CheckpointingMode.EXACTLY_ONCE)
config.set_min_pause_between_checkpoints(30000)
config.set_checkpoint_timeout(120000)
config.set_max_concurrent_checkpoints(1)
config.set_tolerable_checkpoint_failure_number(3)
config.enable_unaligned_checkpoints()
```

## Edge Cases

- **Watermark stalling**: If one partition stops producing events, its watermark stalls all downstream windows. Use `withIdleness(Duration.ofMinutes(5))` to mark idle sources.
- **Window state explosion**: Session windows with no upper bound can accumulate unbounded state. Set a maximum session duration or use state TTL.
- **Clock skew in event time**: Different producers may have different clocks. Bounded out-of-orderness handles small skew; large skew requires per-source watermark tracking.
- **Checkpoint backpressure**: Slow checkpoints cause backpressure. Enable incremental checkpoints with RocksDB and tune checkpoint transfer threads.
- **Topology changes**: Changing stream topology may invalidate checkpoints. Use savepoints for planned upgrades and ensure stable operator UIDs.
