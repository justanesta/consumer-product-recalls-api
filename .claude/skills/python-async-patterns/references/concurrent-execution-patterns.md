# Concurrent Execution Patterns

## asyncio.gather() - Run Multiple Tasks

```python
import asyncio

async def fetch_user(user_id):
    await asyncio.sleep(1)
    return {"id": user_id, "name": f"User{user_id}"}

async def main():
    # Run 3 tasks concurrently
    results = await asyncio.gather(
        fetch_user(1),
        fetch_user(2),
        fetch_user(3)
    )
    print(results)  # All results together

asyncio.run(main())
```

## gather() with Error Handling

```python
async def safe_fetch(url):
    try:
        return await fetch_data(url)
    except Exception as e:
        return {"error": str(e)}

# Collect exceptions as results
results = await asyncio.gather(
    safe_fetch("url1"),
    safe_fetch("url2"),
    return_exceptions=True
)

for result in results:
    if isinstance(result, Exception):
        print(f"Error: {result}")
```

## asyncio.create_task() - Background Tasks

```python
async def background_work(name):
    print(f"{name} started")
    await asyncio.sleep(2)
    print(f"{name} completed")

async def main():
    # Start tasks in background
    task1 = asyncio.create_task(background_work("Task 1"))
    task2 = asyncio.create_task(background_work("Task 2"))
    
    # Do other work
    print("Main work happening...")
    await asyncio.sleep(1)
    
    # Wait for background tasks
    await task1
    await task2

asyncio.run(main())
```

## asyncio.wait() - Fine-grained Control

```python
async def main():
    tasks = [
        asyncio.create_task(fetch_data(url))
        for url in urls
    ]
    
    # Wait for first completion
    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # Process first result
    first_result = done.pop().result()
    print(f"First result: {first_result}")
    
    # Cancel remaining tasks
    for task in pending:
        task.cancel()
```

## TaskGroup (Python 3.11+)

```python
async def main():
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(fetch_data("url1"))
        task2 = tg.create_task(fetch_data("url2"))
    
    # Both tasks completed when context exits
    print(task1.result(), task2.result())
```

## Timeout Handling

```python
# Python 3.11+
async def fetch_with_timeout(url):
    try:
        async with asyncio.timeout(5.0):
            return await fetch_data(url)
    except asyncio.TimeoutError:
        return {"error": "timeout"}

# Pre-3.11
async def fetch_with_timeout_old(url):
    try:
        return await asyncio.wait_for(fetch_data(url), timeout=5.0)
    except asyncio.TimeoutError:
        return {"error": "timeout"}
```

## Semaphore for Rate Limiting

```python
sem = asyncio.Semaphore(5)  # Max 5 concurrent

async def fetch_limited(url):
    async with sem:
        return await fetch_data(url)

async def main():
    urls = [f"url{i}" for i in range(100)]
    # Only 5 requests at a time
    results = await asyncio.gather(*[fetch_limited(url) for url in urls])
```

## Queue for Producer-Consumer

```python
async def producer(queue):
    for i in range(10):
        await queue.put(i)
        await asyncio.sleep(0.1)

async def consumer(queue, name):
    while True:
        item = await queue.get()
        print(f"{name} processing {item}")
        await asyncio.sleep(0.5)
        queue.task_done()

async def main():
    queue = asyncio.Queue()
    
    # Start producer and consumers
    await asyncio.gather(
        producer(queue),
        consumer(queue, "Consumer 1"),
        consumer(queue, "Consumer 2")
    )
