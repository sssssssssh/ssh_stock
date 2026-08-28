.PHONY: install test lint migrate api daily

install:
	python -m pip install -e .[dev]

test:
	pytest

lint:
	ruff check .

migrate:
	alembic upgrade head

api:
	uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

daily:
	PYTHONPATH=backend python -m app.cli daily

