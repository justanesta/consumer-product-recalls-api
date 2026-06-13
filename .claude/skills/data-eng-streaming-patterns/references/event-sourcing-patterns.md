# Event Sourcing Patterns

Detailed patterns for event stores, projections, snapshots, and CQRS implementation with financial transaction scenarios.

## Event Store Implementation

### Event Store Schema

```sql
CREATE TABLE event_store (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  VARCHAR(255) NOT NULL,
    aggregate_id    VARCHAR(255) NOT NULL,
    sequence_number BIGINT NOT NULL,
    event_type      VARCHAR(255) NOT NULL,
    event_data      JSONB NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (aggregate_type, aggregate_id, sequence_number)
);

CREATE INDEX idx_event_store_aggregate
    ON event_store (aggregate_type, aggregate_id, sequence_number);

-- Snapshots for fast aggregate rehydration
CREATE TABLE snapshots (
    aggregate_type  VARCHAR(255) NOT NULL,
    aggregate_id    VARCHAR(255) NOT NULL,
    sequence_number BIGINT NOT NULL,
    state_data      JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (aggregate_type, aggregate_id)
);
```

### Python Event Store Client

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Type
import json, uuid

@dataclass(frozen=True)
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    version: int = 1

class EventStore:
    """Append-only event store with optimistic concurrency."""

    def __init__(self, db_session):
        self.session = db_session

    def append(self, aggregate_type: str, aggregate_id: str,
               events: List[DomainEvent], expected_version: int):
        current_version = self._get_current_version(aggregate_type, aggregate_id)
        if current_version != expected_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, got {current_version}")

        for i, event in enumerate(events):
            self.session.execute(
                """INSERT INTO event_store
                   (aggregate_type, aggregate_id, sequence_number,
                    event_type, event_data, metadata)
                   VALUES (:agg_type, :agg_id, :seq, :evt_type, :evt_data, :meta)""",
                {"agg_type": aggregate_type, "agg_id": aggregate_id,
                 "seq": expected_version + i + 1,
                 "evt_type": type(event).__name__,
                 "evt_data": json.dumps(asdict(event)),
                 "meta": json.dumps({"correlation_id": str(uuid.uuid4())})},
            )
        self.session.commit()

    def load_events(self, aggregate_type: str, aggregate_id: str,
                    after_sequence: int = 0) -> List[dict]:
        rows = self.session.execute(
            """SELECT event_type, event_data, sequence_number FROM event_store
               WHERE aggregate_type = :agg_type AND aggregate_id = :agg_id
                 AND sequence_number > :after_seq
               ORDER BY sequence_number""",
            {"agg_type": aggregate_type, "agg_id": aggregate_id,
             "after_seq": after_sequence},
        ).fetchall()
        return [{"type": r.event_type, "data": json.loads(r.event_data),
                 "sequence": r.sequence_number} for r in rows]
```

## Aggregate with Event Sourcing

```python
@dataclass(frozen=True)
class AccountOpened(DomainEvent):
    account_id: str = ""
    owner: str = ""
    initial_balance: float = 0.0

@dataclass(frozen=True)
class FundsDeposited(DomainEvent):
    account_id: str = ""
    amount: float = 0.0
    reference: str = ""

@dataclass(frozen=True)
class FundsWithdrawn(DomainEvent):
    account_id: str = ""
    amount: float = 0.0
    reference: str = ""

class BankAccount:
    """Event-sourced aggregate -- all state derived from events."""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.balance = 0.0
        self.is_open = False
        self.is_frozen = False
        self.version = 0
        self._pending_events: List[DomainEvent] = []

    def apply(self, event: DomainEvent):
        if isinstance(event, AccountOpened):
            self.is_open = True
            self.balance = event.initial_balance
        elif isinstance(event, FundsDeposited):
            self.balance += event.amount
        elif isinstance(event, FundsWithdrawn):
            self.balance -= event.amount
        self.version += 1

    def deposit(self, amount: float, reference: str):
        if not self.is_open:
            raise AccountNotOpenError("Account is not open")
        if amount <= 0:
            raise ValueError("Deposit must be positive")
        event = FundsDeposited(
            account_id=self.account_id, amount=amount, reference=reference)
        self.apply(event)
        self._pending_events.append(event)

    @classmethod
    def from_events(cls, account_id: str, events: List[DomainEvent]) -> "BankAccount":
        account = cls(account_id)
        for event in events:
            account.apply(event)
        return account
```

## Snapshots

Snapshots avoid replaying the entire event history for aggregates with many events.

```python
class SnapshotRepository:
    def __init__(self, db_session, event_store: EventStore,
                 snapshot_interval: int = 100):
        self.session = db_session
        self.event_store = event_store
        self.snapshot_interval = snapshot_interval

    def load_aggregate(self, aggregate_type: str, aggregate_id: str,
                       aggregate_class: Type) -> object:
        snapshot = self._load_snapshot(aggregate_type, aggregate_id)
        if snapshot:
            aggregate = aggregate_class(aggregate_id)
            aggregate.__dict__.update(snapshot["state"])
            after_seq = snapshot["sequence_number"]
        else:
            aggregate = aggregate_class(aggregate_id)
            after_seq = 0

        events = self.event_store.load_events(
            aggregate_type, aggregate_id, after_sequence=after_seq)
        for event_record in events:
            aggregate.apply(deserialize_event(event_record))
        return aggregate

    def save_aggregate(self, aggregate_type: str, aggregate_id: str,
                       aggregate: object):
        pending = aggregate._pending_events
        if not pending:
            return
        expected_version = aggregate.version - len(pending)
        self.event_store.append(
            aggregate_type, aggregate_id, pending, expected_version)
        if aggregate.version % self.snapshot_interval == 0:
            state = {k: v for k, v in aggregate.__dict__.items()
                     if not k.startswith("_")}
            self.session.execute(
                """INSERT INTO snapshots
                   (aggregate_type, aggregate_id, sequence_number, state_data)
                   VALUES (:agg_type, :agg_id, :seq, :state)
                   ON CONFLICT (aggregate_type, aggregate_id)
                   DO UPDATE SET sequence_number = :seq, state_data = :state""",
                {"agg_type": aggregate_type, "agg_id": aggregate_id,
                 "seq": aggregate.version, "state": json.dumps(state)},
            )
            self.session.commit()
        aggregate._pending_events.clear()
```

## CQRS Read Model Projections

Projections build optimized read models from the event stream.

```python
class AccountBalanceProjection:
    """Maintains a read-optimized balance view from account events."""

    def __init__(self, db_session):
        self.session = db_session

    def handle_event(self, event_type: str, event_data: dict):
        handlers = {
            "AccountOpened": self._on_account_opened,
            "FundsDeposited": self._on_funds_deposited,
            "FundsWithdrawn": self._on_funds_withdrawn,
        }
        handler = handlers.get(event_type)
        if handler:
            handler(event_data)

    def _on_account_opened(self, data: dict):
        self.session.execute(
            """INSERT INTO account_balances (account_id, owner, balance, updated_at)
               VALUES (:id, :owner, :balance, NOW())""",
            {"id": data["account_id"], "owner": data["owner"],
             "balance": data["initial_balance"]})

    def _on_funds_deposited(self, data: dict):
        self.session.execute(
            "UPDATE account_balances SET balance = balance + :amount, updated_at = NOW() WHERE account_id = :id",
            {"id": data["account_id"], "amount": data["amount"]})

    def _on_funds_withdrawn(self, data: dict):
        self.session.execute(
            "UPDATE account_balances SET balance = balance - :amount, updated_at = NOW() WHERE account_id = :id",
            {"id": data["account_id"], "amount": data["amount"]})
```

## Rebuilding Projections

```python
class ProjectionRebuilder:
    def __init__(self, event_store: EventStore, db_session):
        self.event_store = event_store
        self.session = db_session

    def rebuild(self, projection, aggregate_type: str, batch_size: int = 5000):
        """Replay all events for an aggregate type through a projection."""
        self.session.execute(f"TRUNCATE {projection.table_name}")
        offset = 0
        while True:
            events = self.session.execute(
                """SELECT event_type, event_data FROM event_store
                   WHERE aggregate_type = :agg_type ORDER BY sequence_number
                   LIMIT :limit OFFSET :offset""",
                {"agg_type": aggregate_type, "limit": batch_size, "offset": offset},
            ).fetchall()
            if not events:
                break
            for event in events:
                projection.handle_event(event.event_type, json.loads(event.event_data))
            self.session.commit()
            offset += batch_size
```

## Event Schema Evolution

### Upcasting Old Events

```python
class EventUpcaster:
    """Transform old event versions to current format during replay."""

    def upcast(self, event_type: str, event_data: dict, version: int) -> dict:
        if event_type == "FundsDeposited" and version == 1:
            event_data.setdefault("reference", "LEGACY")
        if event_type == "AccountOpened" and version == 1:
            if "name" in event_data and "owner" not in event_data:
                event_data["owner"] = event_data.pop("name")
        return event_data
```

## Edge Cases

- **Concurrency conflicts**: Two commands on the same aggregate may conflict. Optimistic concurrency detects this; the retry strategy depends on the domain.
- **Projection eventual consistency**: Read models lag behind the event store. Design UIs to handle this. For critical reads, query the event store directly.
- **Event store growth**: Append-only stores grow indefinitely. Use snapshots to bound replay time, and archive old events to cold storage.
- **Ordering across aggregates**: Cross-aggregate ordering requires a global sequence or timestamp-based ordering with conflict resolution.
- **Idempotent projections**: Projections must handle replays -- use upserts or track the last processed sequence number.
