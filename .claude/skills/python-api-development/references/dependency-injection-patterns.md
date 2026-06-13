# Dependency Injection Patterns

## Basic Dependencies

```python
from fastapi import Depends

def get_db():
    db = Database()
    try:
        yield db
    finally:
        db.close()

@app.get("/users/")
def get_users(db = Depends(get_db)):
    return db.query("SELECT * FROM users")
```

## Dependencies with Parameters

```python
def verify_token(token: str = Header(...)):
    if token != "secret":
        raise HTTPException(status_code=401)
    return token

def get_current_user(
    token: str = Depends(verify_token),
    db = Depends(get_db)
):
    return db.get_user_by_token(token)

@app.get("/me")
def read_current_user(user = Depends(get_current_user)):
    return user
```

## Class-based Dependencies

```python
class UserService:
    def __init__(self, db = Depends(get_db)):
        self.db = db
    
    def get_user(self, user_id: int):
        return self.db.get_user(user_id)

@app.get("/users/{user_id}")
def get_user(
    user_id: int,
    service: UserService = Depends()
):
    return service.get_user(user_id)
```

## Dependency Override (Testing)

```python
def get_test_db():
    return MockDatabase()

# In tests
app.dependency_overrides[get_db] = get_test_db

# Test
client = TestClient(app)
response = client.get("/users/")
```

## Global Dependencies

```python
# Apply to all routes
app = FastAPI(dependencies=[Depends(verify_token)])

# Or to router
router = APIRouter(dependencies=[Depends(verify_token)])
```
