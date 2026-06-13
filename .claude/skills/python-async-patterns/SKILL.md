---
name: python-async-patterns
description: |
  Modern asynchronous programming with asyncio. Use this skill when building async 
  applications, need concurrent I/O operations, or migrating from sync to async code. 
  Covers async/await syntax, asyncio patterns, aiohttp, async context managers, and 
  common pitfalls.
---

# Python Async Patterns

Modern asynchronous programming patterns with asyncio for Python 3.7+.

## Core Concepts

**Async programming is for I/O-bound concurrency, not CPU-bound parallelism**

Good use cases:
- HTTP requests (API calls, web scraping)
- Database queries
- File I/O
- Network operations

Bad use cases:
- CPU-intensive calculations (use multiprocessing)
- Simple sequential operations

## Basic Async/Await

```python
import asyncio

async def fetch_data(url: str) -> dict:
    await asyncio.sleep(1)  # Simulate I/O
    return {"url": url, "data": "..."}

async def main():
    result = await fetch_data("https://example.com")
    
    # Run multiple coroutines concurrently
    results = await asyncio.gather(
        fetch_data("url1"),
        fetch_data("url2"),
        fetch_data("url3")
    )

asyncio.run(main())
```

## Concurrent Execution Patterns

### asyncio.gather() - Run Multiple Tasks

```python
async def process_urls(urls):
    tasks = [fetch_data(url) for url in urls]
    results = await asyncio.gather(*tasks)
    return results
```

See [concurrent-execution-patterns.md](references/concurrent-execution-patterns.md) for:
- TaskGroup (3.11+)
- Timeout handling
- Semaphores for rate limiting

## Async HTTP with aiohttp

```python
import aiohttp

async def fetch_json(session, url):
    async with session.get(url) as response:
        return await response.json()

async def main():
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            fetch_json(session, "url1"),
            fetch_json(session, "url2")
        )
```

See [aiohttp-patterns.md](references/aiohttp-patterns.md) for:
- POST requests with JSON
- Error handling
- Connection pooling
- Streaming responses

## Async Context Managers

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_session():
    session = aiohttp.ClientSession()
    try:
        yield session
    finally:
        await session.close()
```

## Mixing Sync and Async Code

```python
import concurrent.futures

async def main():
    loop = asyncio.get_event_loop()
    
    # Run blocking code in thread pool
    result = await loop.run_in_executor(
        None,
        blocking_function,
        arg1, arg2
    )
```

See [sync-async-interop.md](references/sync-async-interop.md) for:
- When to use threads vs async
- Event loop management
- Bridging sync and async libraries

## Common Pitfalls

See [async-pitfalls.md](references/async-pitfalls.md) for:
- Forgetting to await
- Blocking the event loop
- Not closing resources
- Race conditions

## When NOT to Use Async

- CPU-bound work (use multiprocessing)
- Simple sequential operations
- Limited external I/O
- Library ecosystem doesn't support async

source: asyncio documentation
