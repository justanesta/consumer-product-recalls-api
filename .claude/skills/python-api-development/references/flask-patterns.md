# Flask Patterns

## Application Factory

```python
from flask import Flask

def create_app(config=None):
    app = Flask(__name__)
    
    if config:
        app.config.from_object(config)
    
    # Register blueprints
    from .api import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")
    
    return app

# Usage
app = create_app("config.ProductionConfig")
```

## Blueprints for Organization

```python
from flask import Blueprint

api_bp = Blueprint("api", __name__)

@api_bp.route("/users")
def get_users():
    return {"users": []}

@api_bp.route("/users/<int:user_id>")
def get_user(user_id):
    return {"user_id": user_id}
```

## Request Handling

```python
from flask import request, jsonify

@app.route("/users", methods=["POST"])
def create_user():
    data = request.get_json()
    
    # Validation
    if not data.get("username"):
        return jsonify({"error": "Username required"}), 400
    
    # Process
    user = User.create(data)
    return jsonify(user.to_dict()), 201
```

## Error Handlers

```python
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

class ValidationError(Exception):
    pass

@app.errorhandler(ValidationError)
def handle_validation_error(error):
    return jsonify({"error": str(error)}), 400
```

## Flask Extensions

```python
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    
    db.init_app(app)
    login_manager.init_app(app)
    
    return app
```
