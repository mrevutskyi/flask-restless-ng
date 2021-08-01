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

check: isort flake8 mypy test

package:
	python3 setup.py sdist bdist_wheel