# Dataclass Examples

## Validation Patterns

```python
from dataclasses import dataclass, field
from typing import ClassVar

@dataclass
class User:
    username: str
    email: str
    age: int
    
    def __post_init__(self):
        """Validate after initialization."""
        if self.age < 0:
            raise ValueError("Age cannot be negative")
        if "@" not in self.email:
            raise ValueError("Invalid email")
        self.username = self.username.lower()

# Usage
user = User("Alice", "alice@example.com", 30)
```

## Inheritance and Composition

```python
@dataclass
class Address:
    street: str
    city: str
    country: str

@dataclass
class Person:
    name: str
    age: int
    address: Address  # Composition

@dataclass
class Employee(Person):
    """Inherits from Person."""
    employee_id: str
    salary: float
    
# Usage
addr = Address("123 Main St", "Boston", "USA")
emp = Employee("Bob", 35, addr, "E001", 75000.0)
```

## Pydantic Integration

```python
from pydantic import BaseModel, Field, field_validator

class UserModel(BaseModel):
    """Pydantic model with validation."""
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    age: int = Field(..., ge=0, le=150)
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Invalid email")
        return v.lower()

# Automatic validation on creation
user = UserModel(username="alice", email="ALICE@EXAMPLE.COM", age=30)
```

## Slots for Memory Optimization

```python
@dataclass(slots=True)  # Python 3.10+
class Point:
    x: float
    y: float
    z: float

# Benefits:
# - Faster attribute access
# - Lower memory usage
# - Prevents adding new attributes
```

## Advanced Features

```python
from dataclasses import dataclass, field, asdict, astuple

@dataclass(frozen=True)  # Immutable
class Config:
    host: str
    port: int = 8080
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict, repr=False)  # Hidden from repr
    _internal: int = field(default=0, init=False)  # Not in __init__
    
    MAX_RETRIES: ClassVar[int] = 3  # Class variable

# Convert to dict/tuple
config = Config("localhost", 9000, ["prod"])
config_dict = asdict(config)
config_tuple = astuple(config)
```

## Factory Pattern

```python
from datetime import datetime

@dataclass
class Event:
    name: str
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

# Each instance gets unique values
event1 = Event("login")
event2 = Event("logout")
# Different timestamps and IDs
```
