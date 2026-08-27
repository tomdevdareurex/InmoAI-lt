.PHONY: install ingest clean-data test lint

install:
	python -m venv venv
	venv/bin/pip install -r requirements.txt

ingest:
	python scripts/ingest_raw.py --source "../real_estate/data/processed"

clean-data:
	python -m inmoai_lt clean

test:
	pytest --cov=src/inmoai_lt --cov-report=term-missing

lint:
	ruff check src tests
