---
name: python-api-development
description: |
  Modern API development with FastAPI and Flask. Use this skill when building REST APIs, 
  need to choose between frameworks, or want to implement authentication, validation, and 
  async endpoints. Covers FastAPI dependency injection, Pydantic validation, Flask patterns, 
  and API design best practices.
---

# Python API Development

Modern patterns for building production-ready APIs with FastAPI and Flask.

## Decision Matrix: FastAPI vs Flask

| Factor | FastAPI | Flask | Winner |
|--------|---------|-------|--------|
| **Performance** | High (async) | Moderate | FastAPI |
| **Auto docs** | Built-in (OpenAPI) | Manual | FastAPI |
| **Validation** | Pydantic (automatic) | Manual/extensions | FastAPI |
| **Learning curve** | Steeper | Gentler | Flask for beginners |
| **Async support** | Native | With extensions | FastAPI |

**General guidance**:
- **Use FastAPI when**: New projects, async needed, want auto-docs, type safety important
- **Use Flask when**: Simple apps, team knows Flask, sync-only fine, want simplicity

## FastAPI Patterns

### Basic API Structure

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.post("/items/")
def create_item(item: Item):
    return item
```

### Pydantic Models for Validation

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    age: int = Field(..., ge=0, le=150)
```

See [pydantic-validation.md](references/pydantic-validation.md) for:
- Custom validators
- Model inheritance
- Nested models

### Dependency Injection

```python
from fastapi import Depends

def get_db():
    db = Database()
    try:
        yield db
    finally:
        db.close()

@app.get("/items/")
def read_items(db = Depends(get_db)):
    return db.get_items()
```

See [dependency-injection-patterns.md](references/dependency-injection-patterns.md) for:
- Class-based dependencies
- Dependency override (testing)
- Sub-dependencies

### Async Endpoints

```python
@app.get("/data/")
async def get_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        return response.json()
```

See [async-api-patterns.md](references/async-api-patterns.md) for:
- When async helps
- Database async patterns
- Concurrent request handling

## Flask Patterns

### Basic Flask API

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/users/<int:user_id>")
def get_user(user_id):
    user = db.get_user(user_id)
    return jsonify(user)
```

See [flask-patterns.md](references/flask-patterns.md) for:
- Application factory pattern
- Flask extensions
- Request hooks

## API Design Best Practices

### RESTful Conventions

```python
GET    /api/users          # List users
POST   /api/users          # Create user
GET    /api/users/123      # Get user
PUT    /api/users/123      # Update user
DELETE /api/users/123      # Delete user
```

### Response Structure

```python
# Success
{"data": {...}, "meta": {"timestamp": "..."}}

# Error
{"error": {"code": "...", "message": "...", "details": [...]}}
```

## Authentication Patterns

See [authentication-patterns.md](references/authentication-patterns.md) for:
- JWT with FastAPI
- OAuth2 with FastAPI
- API keys
- Session-based (Flask)

## Anti-Patterns to Avoid

| Avoid | Use Instead |
|-------|-------------|
| Verbs in URLs (`/getUser`) | Nouns + HTTP methods (`GET /users`) |
| No validation | Pydantic models (FastAPI) |
| Catching all exceptions | Specific error handlers |

source: FastAPI docs, Flask docs, REST API best practices
