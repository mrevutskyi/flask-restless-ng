# Contributing to Flask-Restless-NG

## Development Setup

### Using Python venv (Recommended)

This project uses Python's built-in `venv` module for virtual environment management.

#### Initial Setup

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# Upgrade pip and install build tools
pip install --upgrade pip setuptools wheel

# Install the package in editable mode with all dev dependencies
pip install -e ".[dev,test,doc]"
```

#### Daily Development Workflow

```bash
# Activate the virtual environment
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Your virtual environment is ready!
# You can now run tests, linters, etc.
```

#### Deactivating

```bash
deactivate
```

### Alternative: Using specific requirements files

If you prefer to use the legacy requirements files:

```bash
# Activate venv first
source venv/bin/activate

# Install development dependencies
pip install -r requirements/dev.txt

# Or install for testing only
pip install -r requirements/test-cpython.txt
```

## Running Tests

```bash
# Activate venv first
source venv/bin/activate

# Run all tests
make test
# or
pytest tests/

# Run with coverage
pytest --cov=flask_restless tests/

# Run integration tests (requires Docker)
make integration
```

## Code Quality

```bash
# Activate venv first
source venv/bin/activate

# Run all checks
make check

# Run individual checks
make isort    # Sort imports
make flake8   # Lint code
make mypy     # Type checking
```

## Building the Package

```bash
# Activate venv first
source venv/bin/activate

# Install build tool if not already installed
pip install build

# Build source and wheel distributions
make package
# or
python -m build
```

## IDE Setup

### VS Code

Create `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
    "python.terminal.activateEnvironment": true
}
```

### PyCharm

1. Go to File → Settings → Project → Python Interpreter
2. Click the gear icon → Add
3. Select "Virtualenv Environment" → Existing environment
4. Point to `<project>/venv/bin/python`

## Troubleshooting

### Virtual environment not activating
- Make sure you're in the project root directory
- Check that `venv/bin/activate` exists
- On Windows, you may need to enable script execution: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### Module not found errors
- Ensure the virtual environment is activated
- Reinstall the package: `pip install -e ".[dev,test]"`

### Permission errors on Linux/macOS
- Ensure the activate script is executable: `chmod +x venv/bin/activate`
