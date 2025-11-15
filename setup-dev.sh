#!/bin/bash
# setup-dev.sh - Quick setup script for development environment

set -e

echo "🔧 Setting up Flask-Restless-NG development environment..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed or not in PATH"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✓ Using Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip and setuptools
echo "⬆️  Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel --quiet

# Install the package in editable mode with all dependencies
echo "📥 Installing Flask-Restless-NG in editable mode with dev dependencies..."
pip install -e ".[dev,test,doc]" --quiet

echo ""
echo "✅ Setup complete!"
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "Useful commands:"
echo "  make test          - Run tests"
echo "  make check         - Run all quality checks"
echo "  make package       - Build distribution packages"
echo "  pytest tests/      - Run pytest directly"
echo "  deactivate         - Exit virtual environment"
echo ""
