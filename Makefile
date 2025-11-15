.PHONY: help install install-dev install-test test integration check flake8 isort mypy tox package clean release setup docker-up docker-down docker-logs docker-ps

help:
	@echo "Flask-Restless-NG Development Commands"
	@echo "======================================"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make setup       - Run automated development setup script"
	@echo "  make install     - Install package with all dependencies (dev, test, doc)"
	@echo "  make install-dev - Install package with dev dependencies"
	@echo "  make install-test- Install package with test dependencies only"
	@echo ""
	@echo "Testing:"
	@echo "  make test        - Run all tests (excludes integration)"
	@echo "  make integration - Run integration tests (starts/stops Docker automatically)"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up   - Start MariaDB container"
	@echo "  make docker-down - Stop and remove MariaDB container"
	@echo "  make docker-logs - Show MariaDB container logs"
	@echo "  make docker-ps   - Show running containers"
	@echo ""
	@echo "Code Quality:"
	@echo "  make flake8      - Run flake8 linter"
	@echo "  make isort       - Sort and format imports"
	@echo "  make mypy        - Run type checking"
	@echo "  make tox         - Run tests across Python versions"
	@echo "  make check       - Run all quality checks (isort, flake8, mypy, tox, integration)"
	@echo ""
	@echo "Building:"
	@echo "  make package     - Build source and wheel distributions"
	@echo "  make clean       - Remove build artifacts and cache files"
	@echo "  make release     - Run checks and build package"
	@echo ""

flake8:
	flake8 tests/ flask_restless/

isort:
	isort tests/ flask_restless/

mypy:
	mypy flask_restless/

test:
	pytest tests/

integration:
	@command -v docker-compose >/dev/null 2>&1 && docker-compose up -d mariadb_10_5 || sudo docker-compose up -d mariadb_10_5
	@echo "Waiting for MariaDB to be ready..."
	@sleep 10
	pytest -m integration
	@command -v docker-compose >/dev/null 2>&1 && docker-compose down || sudo docker-compose down

docker-up:
	@command -v docker-compose >/dev/null 2>&1 && docker-compose up -d || sudo docker-compose up -d
	@echo "MariaDB is starting. Wait a few seconds for it to be ready."
	@echo "Check status with: make docker-ps"
	@echo "View logs with: make docker-logs"

docker-down:
	@command -v docker-compose >/dev/null 2>&1 && docker-compose down || sudo docker-compose down

docker-logs:
	@command -v docker-compose >/dev/null 2>&1 && docker-compose logs -f mariadb_10_5 || sudo docker-compose logs -f mariadb_10_5

docker-ps:
	@command -v docker-compose >/dev/null 2>&1 && docker-compose ps || sudo docker-compose ps

check: isort flake8 mypy tox integration

package:
	python3 -m build

tox:
	tox

install:
	pip install -e ".[dev,test,doc]"

install-dev:
	pip install -e ".[dev,test,doc]"

install-test:
	pip install -e ".[test]"

clean:
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

release: check package

setup:
	./setup-dev.sh