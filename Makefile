.PHONY: init fmt test

init:
	python scripts/init_db.py
	python scripts/init_s3.py
	python scripts/init_search.py

fmt:
	ruff check --fix .
	mypy app || true

test:
	pytest -q
