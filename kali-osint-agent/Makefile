.PHONY: install dev up down test run migrate lint format

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

up:
	docker compose up -d

down:
	docker compose down

test:
	pytest -v --cov=src

run:
	kali-agent

migrate:
	alembic upgrade head

lint:
	ruff check src tests

format:
	ruff format src tests
