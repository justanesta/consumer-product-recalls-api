# Pathlib Patterns

## Path Manipulation

```python
from pathlib import Path

# Construction
path = Path("/home/user/documents")
path = Path.home() / "documents" / "file.txt"
path = Path.cwd() / "data"

# Parts
print(path.parent)        # Parent directory
print(path.name)          # file.txt
print(path.stem)          # file
print(path.suffix)        # .txt
print(path.parts)         # ('/home', 'user', 'documents', 'file.txt')
```

## File Operations

```python
# Reading
text = path.read_text()
data = path.read_bytes()
lines = path.read_text().splitlines()

# Writing
path.write_text("Hello, World!")
path.write_bytes(b"Binary data")

# Checking
if path.exists():
    print(f"Size: {path.stat().st_size} bytes")
if path.is_file():
    print("Is a file")
if path.is_dir():
    print("Is a directory")
```

## Glob Patterns

```python
# Find all CSV files
for csv_file in Path("data").glob("*.csv"):
    print(csv_file)

# Recursive search
for py_file in Path(".").rglob("*.py"):
    print(py_file)

# Multiple patterns
from pathlib import Path
import fnmatch

data_files = [
    p for p in Path("data").rglob("*")
    if fnmatch.fnmatch(p.name, "*.csv") or fnmatch.fnmatch(p.name, "*.json")
]
```

## Cross-Platform Paths

```python
# Always works regardless of OS
path = Path("data") / "subdir" / "file.txt"

# Convert to string with proper separators
path_str = str(path)

# Resolve to absolute path
abs_path = path.resolve()

# Relative path
rel_path = Path("data/file.txt").relative_to("data")  # file.txt
```
