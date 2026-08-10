.PHONY: dev dev-infra backend frontend migrate migrate-create test-backend test-frontend clean seed

dev-infra:
	docker-compose up -d postgres redis minio createbuckets

dev: dev-infra
	@echo "Infrastructure running. Start backend and frontend separately."
	@echo "  make backend   — Start FastAPI server"
	@echo "  make frontend  — Start Next.js dev server"

backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

migrate:
	cd backend && alembic upgrade head

migrate-create:
	cd backend && alembic revision --autogenerate -m "$(msg)"

test-backend:
	cd backend && pytest tests/ -v

test-frontend:
	cd frontend && npm run test

clean:
	docker-compose down -v

seed:
	cd backend && python -m app.db.seed
