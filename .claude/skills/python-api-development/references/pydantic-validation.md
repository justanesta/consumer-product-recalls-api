# Pydantic Validation

## Basic Models

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    age: int = Field(..., ge=0, le=150)
    is_active: bool = True
```

## Custom Validators

```python
from pydantic import field_validator

class User(BaseModel):
    username: str
    email: str
    password: str
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Invalid email format")
        return v.lower()
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
```

## Model Config

```python
class User(BaseModel):
    username: str
    email: str
    
    model_config = {
        "str_strip_whitespace": True,
        "str_min_length": 1,
        "frozen": False  # Allow mutations
    }
```

## Nested Models

```python
class Address(BaseModel):
    street: str
    city: str
    country: str

class User(BaseModel):
    name: str
    email: str
    address: Address  # Nested validation

# Usage
user = User(
    name="Alice",
    email="alice@example.com",
    address={
        "street": "123 Main St",
        "city": "Boston",
        "country": "USA"
    }
)
```

## Optional and Union Types

```python
from typing import Optional

class User(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None  # Optional field
    age: int | None = None  # Modern syntax (3.10+)
```

## Validation in FastAPI

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/users/")
def create_user(user: User):
    # Automatic validation
    # If validation fails, FastAPI returns 422 error
    return {"username": user.username, "email": user.email}
```

## Error Handling

```python
from pydantic import ValidationError

try:
    user = User(username="ab", email="invalid", age=200)
except ValidationError as e:
    print(e.json())
    # Detailed error information
```
