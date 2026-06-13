# Aiohttp Patterns

## Basic GET Request

```python
import aiohttp
import asyncio

async def fetch_json(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

result = asyncio.run(fetch_json("https://api.example.com/data"))
```

## Reusing ClientSession

```python
# GOOD - Reuse session for multiple requests
async def fetch_multiple(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_one(session, url) for url in urls]
        return await asyncio.gather(*tasks)

async def fetch_one(session, url):
    async with session.get(url) as response:
        return await response.json()

# BAD - New session per request (slow!)
async def fetch_multiple_bad(urls):
    results = []
    for url in urls:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                results.append(await response.json())
    return results
```

## POST Requests with JSON

```python
async def create_user(user_data):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.example.com/users",
            json=user_data,
            headers={"Content-Type": "application/json"}
        ) as response:
            return await response.json()

result = await create_user({"name": "Alice", "email": "alice@example.com"})
```

## Error Handling

```python
async def safe_fetch(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()  # Raise for 4xx/5xx
                return await response.json()
    except aiohttp.ClientError as e:
        print(f"HTTP error: {e}")
        return None
    except asyncio.TimeoutError:
        print(f"Timeout for {url}")
        return None
```

## Custom Headers and Auth

```python
async def fetch_with_auth(url, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "MyApp/1.0"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            return await response.json()
```

## Streaming Responses

```python
async def download_large_file(url, filename):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            with open(filename, 'wb') as f:
                async for chunk in response.content.iter_chunked(8192):
                    f.write(chunk)
```

## Connection Pooling

```python
# Configure connection limits
connector = aiohttp.TCPConnector(limit=100, limit_per_host=10)
timeout = aiohttp.ClientTimeout(total=30)

async with aiohttp.ClientSession(
    connector=connector,
    timeout=timeout
) as session:
    # Make requests
    pass
```
