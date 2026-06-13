# Sync-Async Interoperability

## Running Sync Code in Async Context

```python
import asyncio
import concurrent.futures

def blocking_io():
    """Blocking I/O operation."""
    import time
    time.sleep(2)
    return "done"

async def main():
    loop = asyncio.get_event_loop()
    
    # Run in thread pool executor
    result = await loop.run_in_executor(
        None,  # Use default ThreadPoolExecutor
        blocking_io
    )
    print(result)

asyncio.run(main())
```

## CPU-Intensive Work in Async

```python
import multiprocessing

def cpu_intensive(n):
    """CPU-bound calculation."""
    return sum(i * i for i in range(n))

async def main():
    loop = asyncio.get_event_loop()
    
    # Use ProcessPoolExecutor for CPU work
    with concurrent.futures.ProcessPoolExecutor() as executor:
        result = await loop.run_in_executor(
            executor,
            cpu_intensive,
            1000000
        )
    print(result)
```

## Running Async Code from Sync Context

```python
# Option 1: asyncio.run() (creates new event loop)
def sync_function():
    result = asyncio.run(async_function())
    return result

# Option 2: Get existing event loop
def sync_function_with_loop():
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(async_function())
    return result
```

## Bridging Sync and Async Libraries

```python
# Wrap sync library in async
async def async_wrapper_for_sync():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_library_call)

# Use sync code in mostly async program
async def main():
    # Async operations
    data1 = await fetch_data()
    
    # Sync operation (non-blocking)
    data2 = await async_wrapper_for_sync()
    
    # More async operations
    result = await process_data(data1, data2)
```

## When to Use Threads vs Async

**Use async when:**
- I/O-bound operations (HTTP, database, files)
- Many concurrent operations
- Operations are naturally async (aiohttp, asyncpg)

**Use threads when:**
- Calling sync libraries that can't be changed
- Blocking I/O that can't be made async
- Mix of sync and async in same codebase

**Use processes when:**
- CPU-intensive calculations
- Need true parallelism
- GIL is a bottleneck
