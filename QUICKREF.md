# Flask-Restless-NG Development Quick Reference

## Virtual Environment

### Setup (One-time)
```bash
# Automated setup
./setup-dev.sh

# OR Manual setup
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev,test,doc]"
```

### Daily Use
```bash
# Activate
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# Deactivate
deactivate
```

### Verify Installation
```bash
python -c "import flask_restless; print(flask_restless.__version__)"
pip list | grep Flask
```

## Common Commands

### Testing
```bash
make test                       # Run all tests
pytest tests/                   # Run pytest directly
pytest tests/test_fetching.py  # Run specific test file
pytest -v                       # Verbose output
pytest --cov=flask_restless     # With coverage
make integration                # Integration tests (auto-starts Docker)
```

### Docker (for Integration Tests)
```bash
make docker-up                  # Start MariaDB container
make docker-down                # Stop MariaDB container
make docker-logs                # View MariaDB logs
make docker-ps                  # Check container status
make integration                # Auto start/stop + run tests
```

### Code Quality
```bash
make check                      # Run all checks
make isort                      # Sort imports
make flake8                     # Lint code
make mypy                       # Type checking
make tox                        # Test across Python versions
```

### Building
```bash
make package                    # Build distributions
make clean                      # Clean build artifacts
python -m build                 # Direct build command
```

### Development
```bash
pip install -e ".[dev]"         # Install with dev dependencies
pip install -e ".[test]"        # Install with test dependencies
pip install -e ".[doc]"         # Install with doc dependencies
pip install -e ".[dev,test,doc]" # Install all
```

## File Structure

```
flask-restless-ng/
├── venv/                       # Virtual environment (git-ignored)
├── flask_restless/             # Main package
│   ├── __init__.py
│   ├── manager.py              # APIManager entry point
│   ├── serialization.py        # JSON API serialization
│   ├── search.py               # Query/filter DSL
│   ├── helpers.py              # SQLAlchemy introspection
│   └── views/                  # Request handlers
├── tests/                      # Test suite
├── pyproject.toml              # Modern build config (PEP 517/518)
├── setup.py                    # Legacy compatibility shim
├── setup-dev.sh                # Quick setup script
├── CONTRIBUTING.md             # Development guide
├── .vscode/settings.json       # VS Code configuration
└── .envrc                      # direnv configuration
```

## VS Code Integration

The project includes `.vscode/settings.json` with:
- Automatic Python interpreter detection (`venv/bin/python`)
- pytest test discovery
- flake8 and mypy linting
- Import organization on save

Just open the project in VS Code and select the venv Python interpreter when prompted.

## PyCharm Integration

1. File → Settings → Project → Python Interpreter
2. Click gear icon → Add → Virtualenv Environment → Existing
3. Select: `<project>/venv/bin/python`

## direnv Integration (Optional)

For automatic venv activation:
```bash
# Install direnv (once)
# Linux: apt install direnv  or  brew install direnv
# Add to ~/.bashrc: eval "$(direnv hook bash)"

# Enable for this project
direnv allow
```

Now venv activates automatically when you `cd` into the project!

## Troubleshooting

### "No module named flask_restless"
```bash
source venv/bin/activate
pip install -e ".[dev,test,doc]"
```

### "Command not found: pytest"
```bash
source venv/bin/activate  # Ensure venv is active
```

### Permission denied on Linux
```bash
chmod +x setup-dev.sh
chmod +x venv/bin/activate
```

### Windows PowerShell execution policy
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Resources

- Documentation: https://flask-restless-ng.readthedocs.org
- Repository: https://github.com/mrevutskyi/flask-restless-ng
- PyPI: https://pypi.org/project/Flask-Restless-NG/
- JSON API Spec: https://jsonapi.org/
