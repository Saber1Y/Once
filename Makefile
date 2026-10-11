.PHONY: install web serve dev demo drift repeat test lint

install:
	uv sync
	cd web && npm ci

web:
	cd web && npm run build

serve: web
	uv run once serve

dev:
	cd web && npm run dev

demo:
	uv run once demo

drift:
	uv run once drift

repeat:
	uv run once repeat T-102 -n 10

test:
	uv run pytest -q

lint:
	uv run ruff check src tests
	cd web && npx eslint src && npx tsc -b
