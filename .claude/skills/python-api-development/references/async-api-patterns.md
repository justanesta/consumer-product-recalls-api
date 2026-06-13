# Async API Patterns

## Async Route Handlers

```python
@app.get("/users/")
async def get_users():
    # Use await for async operations
    users = await database.fetch_all("SELECT * FROM users")
    return users
```

## Async Database Operations

```python
from databases import Database

database = Database("postgresql://...")

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    query = "SELECT * FROM users WHERE id = :id"
    user = await database.fetch_one(query, values={"id": user_id})
    return user
```

## Concurrent Operations

```python
import asyncio

@app.get("/dashboard")
async def get_dashboard():
    # Run multiple queries concurrently
    users, orders, stats = await asyncio.gather(
        database.fetch_all("SELECT * FROM users"),
        database.fetch_all("SELECT * FROM orders"),
        database.fetch_one("SELECT COUNT(*) FROM visits")
    )
    return {"users": users, "orders": orders, "stats": stats}
```

## Async External API Calls

```python
import httpx

@app.get("/external-data")
async def get_external_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        return response.json()
```

## When to Use Async

**Use async when:**
- Database I/O operations
- External API calls
- File operations (with aiofiles)
- Multiple concurrent operations

**Don't use async when:**
- CPU-intensive calculations
- Synchronous libraries only
- Simple CRUD without I/O
```
