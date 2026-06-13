# Authentication Patterns

## JWT with FastAPI

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

SECRET_KEY = "your-secret-key"
security = HTTPBearer()

def create_token(user_id: int) -> str:
    payload = {"user_id": user_id}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/protected")
def protected_route(payload = Depends(verify_token)):
    return {"user_id": payload["user_id"]}

@app.post("/login")
def login(username: str, password: str):
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user.id)
    return {"access_token": token}
```

## OAuth2 with FastAPI

```python
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401)
    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/users/me")
def read_current_user(token: str = Depends(oauth2_scheme)):
    user = get_user_from_token(token)
    return user
```

## API Keys

```python
from fastapi import Header, HTTPException

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != "valid-api-key":
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

@app.get("/data")
def get_data(api_key: str = Depends(verify_api_key)):
    return {"data": "protected"}
```

## Session-based (Flask)

```python
from flask import session
from flask_login import login_user, logout_user, login_required

@app.route("/login", methods=["POST"])
def login():
    user = User.query.filter_by(username=request.form["username"]).first()
    if user and user.check_password(request.form["password"]):
        login_user(user)
        return redirect("/dashboard")
    return "Invalid credentials", 401

@app.route("/protected")
@login_required
def protected():
    return "Protected data"
```
