flake8:
	flake8 tests/ flask_restless/

isort:
	isort tests/ flask_restless/

mypy:
	mypy flask_restless/

test:
	pytest tests/

integration:
	docker start mariadb_10_5
	pytest -m integration
	docker stop mariadb_10_5

check: isort flake8 mypy tox integration

package:
	python3 -m build

tox:
	tox

clean:
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

release: check package