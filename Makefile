setup:
	docker compose build
	docker compose up -d
	make migrate

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f app

logs-app:
	docker compose logs -f app

logs-postgres:
	docker compose logs -f postgres

logs-redis:
	docker compose logs -f redis

shell:
	docker compose exec app /bin/bash

migrate:
	docker compose exec app alembic upgrade head

backup-db:
	docker compose exec postgres pg_dump -U $$POSTGRES_USER $$POSTGRES_DB > ./pg_backup.sql

health:
	curl --fail http://localhost:8000/health && echo "OK" || echo "FAIL"

up-admin:
	docker compose up -d pgadmin redis-commander

prod:
	docker compose -f docker-compose.yml up -d --build --remove-orphans

remove-data:
	docker compose down -v
