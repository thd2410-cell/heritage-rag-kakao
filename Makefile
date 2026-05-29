.PHONY: dev-up dev-down prod-up prod-down prod-logs prod-ps ci-check deploy backup

dev-up:
	docker compose up --build

dev-down:
	docker compose down

prod-up:
	docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml --env-file .env.production down

prod-logs:
	docker compose -f docker-compose.prod.yml --env-file .env.production logs -f --tail=200

prod-ps:
	docker compose -f docker-compose.prod.yml --env-file .env.production ps

ci-check:
	python3 -m compileall backend/app scripts/collect_heritages.py
	docker compose config >/dev/null
	docker compose -f docker-compose.prod.yml --env-file .env.production.example config >/dev/null

deploy:
	./scripts/deploy.sh

backup:
	./scripts/backup_db.sh
