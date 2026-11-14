SHELL := /bin/bash
ENV ?= dev
YEAR ?= 2024
COMPOSE = $(if $(AIRFLOW_IMAGE),AIRFLOW_IMAGE=$(AIRFLOW_IMAGE) )docker compose --env-file env/versions.env --env-file env/.env.$(ENV) -p sdg-$(ENV)


.PHONY: ensure-image env build up down destroy verify run load-2025 deploy test lint e2e logs

env:
	scripts/gen_env.sh $(ENV)

build:
	set -a; . env/versions.env; set +a; \
	docker build -f docker/airflow/Dockerfile --build-arg AIRFLOW_VERSION=$$AIRFLOW_VERSION \
	  -t $(or $(AIRFLOW_IMAGE),sdg-airflow:local) .

ensure-image:
	@if [ -z "$(AIRFLOW_IMAGE)" ]; then docker image inspect sdg-airflow:local >/dev/null 2>&1 || $(MAKE) build; fi

up: ensure-image
	$(COMPOSE) up -d --wait

down:
	$(COMPOSE) down

destroy:
	@if [ "$(FORCE)" != "1" ]; then \
	  read -r -p "Esto elimina TODOS los datos del entorno $(ENV). Escribe '$(ENV)' para confirmar: " a; \
	  [ "$$a" = "$(ENV)" ] || { echo "Cancelado"; exit 1; }; \
	fi
	$(COMPOSE) --profile tools down -v

verify:
	scripts/verify_stack.sh $(ENV)

run:
	$(COMPOSE) exec -T airflow-scheduler mdf run --metadata /opt/airflow/metadata/metadata.json --param year=$(YEAR)

load-2025:
	$(COMPOSE) run --rm -T mc-client cp /seed/data2025.csv local/data/demo/input/data2025.csv

deploy:
	$(COMPOSE) pull --ignore-buildable --ignore-pull-failures
	$(COMPOSE) up -d --wait

test:
	.venv/bin/pytest --cov=src/mdf --cov=checks --cov-report=term-missing --cov-fail-under=80

lint:
	pre-commit run --all-files

e2e:
	PYTHON=$(if $(wildcard .venv/bin/python),$(CURDIR)/.venv/bin/python,python3) tests/e2e/run_e2e.sh $(ENV)

logs:
	$(COMPOSE) logs -f
