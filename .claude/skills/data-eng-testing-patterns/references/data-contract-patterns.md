# Data Contract Patterns

Patterns for defining, versioning, and testing data contracts between producers and consumers.

## What is a Data Contract

A data contract is a formal agreement between a data producer and its consumers specifying schema, semantics, SLAs, and ownership. Contracts prevent breaking changes from silently propagating through the data platform.

## JSON Schema Contracts

### Defining a Contract

```json
{
  "$id": "https://data.company.com/contracts/orders/v2.1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Orders Contract",
  "type": "object",
  "properties": {
    "order_id": {"type": "integer"},
    "customer_id": {"type": "integer"},
    "order_total": {"type": "number", "minimum": 0},
    "status": {"type": "string", "enum": ["pending", "completed", "refunded", "cancelled"]},
    "created_at": {"type": "string", "format": "date-time"},
    "line_items": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "properties": {
          "product_id": {"type": "integer"},
          "quantity": {"type": "integer", "minimum": 1},
          "unit_price": {"type": "number", "minimum": 0}
        },
        "required": ["product_id", "quantity", "unit_price"]
      }
    }
  },
  "required": ["order_id", "customer_id", "order_total", "status", "created_at"]
}
```

### Validating DataFrames Against JSON Schema

```python
import jsonschema
import json

def validate_dataframe_against_contract(
    df: pd.DataFrame, contract_path: str, sample_size: int = 1000,
) -> list[str]:
    with open(contract_path) as f:
        schema = json.load(f)
    errors = []
    required = schema.get("required", [])
    missing = [col for col in required if col not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {missing}")

    for idx, row in df.head(sample_size).iterrows():
        try:
            jsonschema.validate(instance=row.to_dict(), schema=schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Row {idx}: {e.message}")
            if len(errors) > 50:
                break
    return errors

def test_orders_matches_contract(orders_df):
    errors = validate_dataframe_against_contract(orders_df, "contracts/orders_v2.1.0.json")
    assert not errors, f"Contract violations:\n" + "\n".join(errors)
```

## Avro Schema Contracts

```json
{
  "type": "record",
  "name": "Order",
  "namespace": "com.company.data.orders",
  "fields": [
    {"name": "order_id", "type": "long"},
    {"name": "customer_id", "type": "long"},
    {"name": "order_total", "type": {"type": "bytes", "logicalType": "decimal", "precision": 10, "scale": 2}},
    {"name": "status", "type": {"type": "enum", "name": "OrderStatus", "symbols": ["PENDING", "COMPLETED", "REFUNDED", "CANCELLED"]}},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

### Testing Avro Compatibility

```python
from confluent_kafka.schema_registry import SchemaRegistryClient

def test_schema_is_backward_compatible():
    client = SchemaRegistryClient({"url": "http://localhost:8081"})
    with open("contracts/orders_v3.avsc") as f:
        new_schema = f.read()
    is_compatible = client.test_compatibility(
        subject_name="orders-value", schema=Schema(new_schema, "AVRO"),
    )
    assert is_compatible, "New schema is not backward compatible"
```

## Contract Versioning

### Detecting Breaking Changes Automatically

```python
def detect_breaking_changes(old_contract: dict, new_contract: dict) -> list[str]:
    breaking = []
    old_cols = set(old_contract.get("required", []))
    new_cols = set(new_contract.get("required", []))

    removed = old_cols - new_cols
    if removed:
        breaking.append(f"Removed required columns: {removed}")

    old_props = old_contract.get("properties", {})
    new_props = new_contract.get("properties", {})
    for col in old_props:
        if col in new_props:
            if old_props[col].get("type") != new_props[col].get("type"):
                breaking.append(f"Column '{col}' type changed")
            old_enum = set(old_props[col].get("enum", []))
            new_enum = set(new_props[col].get("enum", []))
            if old_enum and new_enum and (old_enum - new_enum):
                breaking.append(f"Column '{col}' removed enum values: {old_enum - new_enum}")
    return breaking

def test_no_breaking_changes():
    old = load_contract("contracts/orders_v2.0.0.json")
    new = load_contract("contracts/orders_v2.1.0.json")
    breaking = detect_breaking_changes(old, new)
    assert not breaking, f"Breaking changes:\n" + "\n".join(breaking)
```

## Backward and Forward Compatibility

| Change | Backward Compatible | Forward Compatible |
|--------|--------------------|--------------------|
| Add optional column | Yes | Yes |
| Add required column | No | Yes |
| Remove optional column | Yes | No |
| Remove required column | No | No |
| Widen type (int -> float) | Yes | No |
| Narrow type (float -> int) | No | Yes |
| Add enum value | Yes | No |
| Remove enum value | No | Yes |

### Testing Backward Compatibility

```python
def test_backward_compatibility(new_contract, sample_old_data):
    errors = validate_dataframe_against_contract(sample_old_data, new_contract)
    assert not errors, f"New contract rejects old data:\n" + "\n".join(errors)

def test_forward_compatibility(old_contract, sample_new_data):
    known_columns = list(old_contract["properties"].keys())
    filtered = sample_new_data[[c for c in sample_new_data.columns if c in known_columns]]
    errors = validate_dataframe_against_contract(filtered, old_contract)
    assert not errors, f"Forward compatibility broken:\n" + "\n".join(errors)
```

## Producer and Consumer Test Responsibilities

### Producer Tests

```python
class TestOrdersProducer:
    def test_output_matches_published_contract(self, pipeline_output):
        contract = load_latest_contract("orders")
        errors = validate_dataframe_against_contract(pipeline_output, contract)
        assert not errors

    def test_no_breaking_changes_in_pr(self):
        current = load_contract("contracts/orders_current.json")
        proposed = load_contract("contracts/orders_proposed.json")
        breaking = detect_breaking_changes(current, proposed)
        assert not breaking, "PR introduces breaking changes. Coordinate with consumers."

    def test_sla_freshness(self, pipeline_metadata):
        delay = pipeline_metadata["completion_time"] - pipeline_metadata["scheduled_time"]
        assert delay.total_seconds() < 3600, "Pipeline exceeded 1-hour SLA"
```

### Consumer Tests

```python
class TestAnalyticsConsumer:
    def test_can_read_with_current_contract(self, orders_source):
        df = read_orders(orders_source)
        assert "order_id" in df.columns
        assert df["order_total"].dtype == float

    def test_handles_new_optional_fields_gracefully(self):
        df = pd.DataFrame({
            "order_id": [1], "customer_id": [100], "order_total": [50.0],
            "status": ["completed"], "created_at": ["2025-03-01T00:00:00Z"],
            "new_unknown_field": ["surprise"],
        })
        result = transform_orders(df)  # Should not raise
        assert len(result) == 1
```

## Contract Registry Pattern

```python
class ContractRegistry:
    def __init__(self, contracts_dir: str):
        self.contracts_dir = Path(contracts_dir)
        self._cache: dict[str, dict] = {}

    def get_contract(self, name: str, version: str = "latest") -> dict:
        cache_key = f"{name}:{version}"
        if cache_key not in self._cache:
            if version == "latest":
                versions = sorted(self.contracts_dir.glob(f"{name}_v*.json"))
                path = versions[-1]
            else:
                path = self.contracts_dir / f"{name}_{version}.json"
            with open(path) as f:
                self._cache[cache_key] = json.load(f)
        return self._cache[cache_key]

    def validate(self, name: str, df: pd.DataFrame, version: str = "latest") -> list[str]:
        contract = self.get_contract(name, version)
        return validate_dataframe_against_contract(df, contract)
```
