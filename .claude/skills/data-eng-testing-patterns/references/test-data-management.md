# Test Data Management

Patterns for creating, managing, and organizing test data including fixtures, factories, synthetic data generation, and anonymization.

## Factory Pattern for Test Data

### Basic Factory Functions

```python
from datetime import datetime, timedelta
from typing import Any
import uuid

def make_customer(
    customer_id: int | None = None,
    name: str = "Test Customer",
    email: str | None = None,
    segment: str = "standard",
    signup_date: str = "2025-01-01",
    is_active: bool = True,
    **overrides: Any,
) -> dict:
    cid = customer_id or abs(hash(uuid.uuid4())) % 100000
    return {
        "customer_id": cid, "name": name,
        "email": email or f"customer_{cid}@example.com",
        "segment": segment, "signup_date": signup_date,
        "is_active": is_active, **overrides,
    }

def make_order(
    order_id: int | None = None, customer_id: int = 1000,
    amount: float = 99.99, status: str = "completed",
    created_at: str = "2025-03-01 10:00:00", **overrides: Any,
) -> dict:
    return {
        "order_id": order_id or abs(hash(uuid.uuid4())) % 1000000,
        "customer_id": customer_id, "amount": amount,
        "status": status, "created_at": created_at, **overrides,
    }
```

### Using Factories in Tests

```python
def test_high_value_customer_discount():
    customer = make_customer(segment="enterprise")
    order = make_order(customer_id=customer["customer_id"], amount=5000.00)
    discount = calculate_discount(customer, order)
    assert discount == 0.15

def test_inactive_customer_cannot_place_order():
    customer = make_customer(is_active=False)
    order = make_order(customer_id=customer["customer_id"])
    with pytest.raises(InactiveCustomerError):
        place_order(customer, order)
```

### Batch Factory for DataFrames

```python
class OrderFactory:
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self._counter = 0

    def create(self, n: int = 1, **overrides) -> pd.DataFrame:
        records = []
        for _ in range(n):
            self._counter += 1
            record = {
                "order_id": self._counter,
                "customer_id": int(self.rng.integers(1000, 9999)),
                "amount": round(float(self.rng.lognormal(4, 0.8)), 2),
                "status": self.rng.choice(["completed", "pending", "refunded"], p=[0.7, 0.2, 0.1]),
                "created_at": (datetime(2025, 1, 1) + timedelta(days=int(self.rng.integers(0, 90)))).isoformat(),
            }
            record.update(overrides)
            records.append(record)
        return pd.DataFrame(records)

    def create_with_nulls(self, n: int = 100, null_rate: float = 0.05) -> pd.DataFrame:
        df = self.create(n)
        mask = self.rng.random((len(df), len(df.columns))) < null_rate
        for i, col in enumerate(df.columns):
            if col != "order_id":
                df.loc[mask[:, i], col] = None
        return df
```

## Synthetic Data Generation

### Using Faker for Realistic Data

```python
from faker import Faker
import numpy as np

fake = Faker()

def generate_customers(n: int = 1000, seed: int = 42) -> pd.DataFrame:
    Faker.seed(seed)
    np.random.seed(seed)
    records = []
    for i in range(n):
        records.append({
            "customer_id": i + 1,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": fake.unique.email(),
            "city": fake.city(),
            "state": fake.state_abbr(),
            "signup_date": fake.date_between(start_date="-2y", end_date="today"),
            "segment": np.random.choice(
                ["enterprise", "mid_market", "smb", "individual"],
                p=[0.05, 0.15, 0.30, 0.50],
            ),
        })
    return pd.DataFrame(records)
```

### Generating Data with Known Aggregates

```python
def generate_orders_with_known_aggregates(
    total_revenue: float = 100000.0,
    n_orders: int = 1000,
    refund_rate: float = 0.08,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate orders where we know the expected aggregates for testing."""
    np.random.seed(seed)
    n_refunded = int(n_orders * refund_rate)
    n_completed = n_orders - n_refunded

    weights = np.random.dirichlet(np.ones(n_completed))
    completed_amounts = (weights * total_revenue).round(2)

    records = [{"order_id": i + 1, "amount": completed_amounts[i], "status": "completed"}
               for i in range(n_completed)]
    records += [{"order_id": n_completed + i + 1,
                 "amount": round(np.random.uniform(10, 500), 2), "status": "refunded"}
                for i in range(n_refunded)]
    return pd.DataFrame(records)

def test_revenue_aggregation():
    df = generate_orders_with_known_aggregates(total_revenue=100000.0)
    result = calculate_total_revenue(df)
    assert abs(result - 100000.0) < 1.0
```

## Data Anonymization

### Column-Level Anonymization

```python
import hashlib

class DataAnonymizer:
    def __init__(self, salt: str = "test-salt-2025", seed: int = 42):
        self.salt = salt
        Faker.seed(seed)

    def hash_value(self, value: str) -> str:
        return hashlib.sha256(f"{self.salt}:{value}".encode()).hexdigest()[:16]

    def anonymize_email(self, email: str) -> str:
        local, domain = email.split("@")
        return f"{self.hash_value(local)}@{domain}"

    def anonymize_dataframe(self, df: pd.DataFrame, column_rules: dict[str, str]) -> pd.DataFrame:
        """Rules: "email", "name", "hash", "drop", "fake"."""
        result = df.copy()
        for col, rule in column_rules.items():
            if col not in result.columns:
                continue
            if rule == "email":
                result[col] = result[col].apply(self.anonymize_email)
            elif rule == "hash":
                result[col] = result[col].apply(self.hash_value)
            elif rule == "drop":
                result = result.drop(columns=[col])
            elif rule == "fake":
                result[col] = [fake.address() for _ in range(len(result))]
        return result

# Usage
anonymizer = DataAnonymizer()
test_data = anonymizer.anonymize_dataframe(prod_sample, {
    "email": "email", "phone": "hash", "ssn": "drop", "address": "fake",
})
```

### Referential Integrity Preservation

```python
def anonymize_with_referential_integrity(
    tables: dict[str, pd.DataFrame],
    id_columns: dict[str, list[str]],
) -> dict[str, pd.DataFrame]:
    """Anonymize IDs consistently across related tables."""
    id_maps: dict[str, dict] = {}
    result = {}
    for table_name, df in tables.items():
        anonymized = df.copy()
        for col in id_columns.get(table_name, []):
            if col not in id_maps:
                unique_vals = set()
                for t_df in tables.values():
                    if col in t_df.columns:
                        unique_vals.update(t_df[col].dropna().unique())
                id_maps[col] = {old: idx + 1 for idx, old in enumerate(sorted(unique_vals))}
            anonymized[col] = anonymized[col].map(id_maps[col])
        result[table_name] = anonymized
    return result
```

## Fixture File Organization

```
tests/
├── fixtures/
│   ├── raw/                        # Raw source data fixtures
│   │   ├── orders.parquet
│   │   └── customers.parquet
│   ├── expected/                   # Expected output for regression tests
│   │   └── daily_revenue.parquet
│   ├── edge_cases/                 # Boundary conditions
│   │   ├── empty_orders.parquet
│   │   └── null_heavy_customers.parquet
│   └── contracts/                  # Contract schema definitions
│       └── orders_v2.1.0.json
├── factories/
│   ├── order_factory.py
│   └── customer_factory.py
└── conftest.py
```

### Conftest for Fixture Loading

```python
FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture(scope="session")
def raw_orders():
    return pd.read_parquet(FIXTURES_DIR / "raw" / "orders.parquet")

@pytest.fixture(scope="session")
def expected_daily_revenue():
    return pd.read_parquet(FIXTURES_DIR / "expected" / "daily_revenue.parquet")

@pytest.fixture
def empty_orders():
    return pd.read_parquet(FIXTURES_DIR / "edge_cases" / "empty_orders.parquet")
```

## Seeded Random Generation

```python
def create_reproducible_dataset(seed: int = 42) -> pd.DataFrame:
    """Every call with the same seed produces identical output."""
    np.random.seed(seed)
    Faker.seed(seed)
    fake = Faker()
    n = 1000
    return pd.DataFrame({
        "id": range(1, n + 1),
        "name": [fake.name() for _ in range(n)],
        "amount": np.random.lognormal(4, 1, n).round(2),
        "category": np.random.choice(["A", "B", "C"], n, p=[0.5, 0.3, 0.2]),
    })

@pytest.mark.parametrize("seed", [42, 123, 456, 789])
def test_pipeline_stable_across_data_variations(seed):
    df = create_reproducible_dataset(seed=seed)
    result = run_pipeline(df)
    assert result["revenue"].sum() >= 0
    assert not result.isnull().any().any()
```
