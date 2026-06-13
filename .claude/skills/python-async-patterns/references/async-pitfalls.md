# Async Pitfalls

## Forgetting to Await

```python
# BAD - Returns coroutine object, doesn't execute
async def main():
    result = fetch_data()  # Forgot await!
    print(result)  # <coroutine object>

# GOOD
async def main():
    result = await fetch_data()
    print(result)  # Actual data
```

## Blocking the Event Loop

```python
# BAD - Blocks event loop
import time

async def bad_sleep():
    time.sleep(2)  # Blocks everything!
    return "done"

# GOOD - Yields control
async def good_sleep():
    await asyncio.sleep(2)  # Non-blocking
    return "done"

# BAD - Blocking I/O
async def bad_read():
    with open("file.txt") as f:  # Blocks!
        return f.read()

# GOOD - Async I/O
import aiofiles

async def good_read():
    async with aiofiles.open("file.txt") as f:
        return await f.read()
```

## Creating Multiple Event Loops

```python
# BAD - Multiple event loops
def main():
    asyncio.run(task1())  # Creates event loop
    asyncio.run(task2())  # Creates another event loop!

# GOOD - Single event loop
async def main():
    await task1()
    await task2()

asyncio.run(main())
```

## Not Closing Resources

```python
# BAD - Session not closed
session = aiohttp.ClientSession()
response = await session.get(url)

# GOOD - Use context manager
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()
```

## Race Conditions

```python
# BAD - Race condition
counter = 0

async def increment():
    global counter
    temp = counter
    await asyncio.sleep(0.01)
    counter = temp + 1

# GOOD - Use asyncio.Lock
lock = asyncio.Lock()
counter = 0

async def increment():
    global counter
    async with lock:
        temp = counter
        await asyncio.sleep(0.01)
        counter = temp + 1
```

## Not Handling Exceptions

```python
# BAD - Unhandled exceptions
results = await asyncio.gather(
    fetch_data("url1"),
    fetch_data("url2")  # If this fails, entire gather fails
)

# GOOD - Handle exceptions
async def safe_fetch(url):
    try:
        return await fetch_data(url)
    except Exception as e:
        return {"error": str(e)}

results = await asyncio.gather(
    safe_fetch("url1"),
    safe_fetch("url2")
)
```

## Common Mistakes Summary

| Mistake | Impact | Fix |
|---------|--------|-----|
| Forget `await` | Coroutine never executes | Always `await` coroutines |
| `time.sleep()` | Blocks event loop | Use `asyncio.sleep()` |
| Regular file I/O | Blocks event loop | Use `aiofiles` |
| Multiple `asyncio.run()` | Slow, inefficient | Single event loop |
| No exception handling | Crashes on errors | Try/except or `return_exceptions=True` |
