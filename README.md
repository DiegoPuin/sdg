# Plataforma de datos local + framework metadata-driven

Stack Docker por entorno (Airflow, Postgres, Silo), framework Python `mdf` dirigido por `metadata/metadata.json`, dos checks independientes, un DAG y pipelines de CI/CD.

## Requisitos
- Docker con Compose v2 y `make`.
- Python 3.12 para desarrollo local, tests y checks: `python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'`.
- Los CSV `data/data2024.csv` y `data/data2025.csv`.

## Arranque rápido
```bash
make env up verify ENV=dev     # genera secretos, construye la imagen si falta, levanta y verifica
```
`make up` construye la imagen local `sdg-airflow:local` si no existe (`make build` la reconstruye tras cambios de código). Termina con `VERIFY OK`.

## Puertos por entorno (solo `127.0.0.1`)

| Servicio | dev | prod |
|---|---|---|
| Airflow UI | 8080 | 8081 |
| Postgres | 5432 | 5433 |
| Silo API | 9000 | 9100 |
| Silo consola | 9001 | 9101 |

Usuario de Airflow: `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` de `env/.env.<ENV>`. Consola de Silo: usuario de servicio `SILO_APP_ACCESS_KEY` / `SILO_APP_SECRET_KEY`.

## Ejecutar el framework
```bash
make run ENV=dev YEAR=2024
make load-2025 ENV=dev          # o subir data2025.csv a mano en la consola de Silo (data/demo/input/)
make run ENV=dev YEAR=2025
```
Resultados esperados: `last` 15.410 → 15.410; `historic` 15.410 → 30.820; `demo` 15.410 → 15.410 (merge: 0 insertadas, 5 actualizadas, 15.405 sin cambio); `raw_demo` 15.410 → 30.820. Ejecutar dos veces el mismo año duplica filas en los outputs `append` (comportamiento documentado, sin protección).

`mdf validate --metadata metadata/metadata.json --param year=2024` valida sin leer ni escribir. Códigos de salida: 0 OK · 2 metadata inválida · 3 lectura · 4 transformación · 5 escritura.

## Ejecutar el DAG
En la UI de Airflow, DAG `mdf_run` → Trigger con `year` 2024 y luego 2025 (despausarlo la primera vez). Tareas: `check_input` → `run_dataflow`. Si falta el archivo del año, `check_input` falla con la ruta completa tras 2 reintentos.

## Ejecutar los checks
```bash
python checks/diff_rows.py --old data/data2024.csv --new data/data2025.csv      # 0 añadidas, 0 eliminadas, 8 cambiadas
python checks/dq_both_sexes.py --file data/data2024.csv                          # STATUS: OK
python checks/dq_both_sexes.py --file data/data2025.csv                          # STATUS: PENDING_REVIEW, exit 1
```
Los CSV de resultado quedan en `./out`.

## Tests
`make test` (unitarios + cobertura ≥ 80 %). `make e2e ENV=dev` levanta un stack limpio, ejecuta las rutas A (CLI) y B (DAG) y los checks, y destruye el entorno al terminar (guarda logs en `e2e-logs/` si falla). `make lint` ejecuta `pre-commit run --all-files`.

## Guion de demo

| Paso | Entorno | Acción |
|---|---|---|
| 1 | dev | `make env up verify ENV=dev`; abrir la UI de Airflow y mostrar las conexiones |
| 2 | dev | `make run ENV=dev YEAR=2024`; mostrar 15.410 filas en `last`, `historic`, `demo`, `raw_demo` |
| 3 | dev | Subir `data2025.csv` a mano en la consola de Silo; `make run ENV=dev YEAR=2025`; mostrar los conteos y el log del merge |
| 4 | prod | `make env up verify ENV=prod`; mismo recorrido con el DAG `mdf_run` desde la UI (`year` 2024 y luego 2025) |
| 5 | local | Ejecutar los checks A y B |
| 6 | dev | `make down` y `make up`: los datos persisten |
| 7 | GitHub | Mostrar `ci.yml` y `cd.yml` |

## Protección de rama (`main`)
Configurar en GitHub: todos los jobs de `ci.yml` (`lint`, `compose-validate`, `iac-security`, `deps-audit`, `test`, `build`, `dag-validate`) como *required checks*; sin push directo; al menos 1 aprobación. El despliegue (`cd.yml`) usa los environments `dev` y `prod` (revisores requeridos en `prod`), la variable `ENABLE_DEPLOY=true` para activarlo, la variable de environment `PREV_IMAGE` (prod) y el secreto `VARS_ADMIN_TOKEN` para actualizarla. Sustituir `@OWNER` en `.github/CODEOWNERS`.

## Decisiones principales
- Un único `compose.yaml`; el entorno solo cambia el `.env` (`ENV=dev|prod`, proyecto `sdg-<env>`), sin `container_name` ni nombres fijos de red o volumen.
- LocalExecutor, sin broker ni triggerer. Sin código por bind-mount: el DAG, el metadata y las conexiones van dentro de la imagen.
- Conexiones de Airflow como un JSON por archivo en `connections/`, con variables de entorno expandidas al arrancar; nunca secretos literales.
- El framework separa metadata (pydantic), grafo (orden topológico con `waits`), registros extensibles de lectores/transformaciones/escritores y SQL puro para las tablas.
- Despliegue siempre por digest de imagen, solo tras la integración.
- Diagramas en [docs/diagrams.md](docs/diagrams.md); propuesta AWS en [docs/aws-proposal.md](docs/aws-proposal.md); plantilla en `cloudformation/data-security.yaml`.

## Supuestos
- **Versiones fijadas** (`env/versions.env`): Airflow 3.4.0, `postgres:18.7-alpine`, Silo `RELEASE.2026-11-12T00-00-00Z`, `mc` de la misma release.
- **`metadata/metadata.json` sigue el Apéndice A del spec.** El `data/metadata.json` aportado difiere: no incluye `"thousands": "."` en las opciones de `demo_data`. Sin esa opción `total` se lee como decimal (`1.932` → 1,932) y los conteos y tipos esperados no se cumplen, por lo que se usa la versión del apéndice. `data/metadata.json` no se ha tocado.
- Postgres 18 declara `VOLUME /var/lib/postgresql`; se fija `PGDATA=/var/lib/postgresql/data/pgdata` para que `pgdata` persista de verdad.
- Silo y Postgres arrancan con el usuario por defecto de su imagen (Silo necesita escribir en `/data`; el entrypoint de Postgres baja privilegios por sí mismo). Todos los servicios llevan `no-new-privileges`.
- Auth manager FAB (`apache-airflow-providers-fab`); `AIRFLOW__API__SECRET_KEY` reutiliza `AIRFLOW_JWT_SECRET`.
- Healthcheck del apiserver: `/api/v2/monitor/health`. Healthcheck de Silo: `silo healthcheck ready`.
- `mc admin policy create` + `attach --user` y `mc admin user add` verificados contra la imagen `mc` pinneada; `airflow connections import --overwrite` existe en 3.4.0.
- El servicio `mc-client` (perfil `tools`) usa las credenciales del usuario de servicio para `make load-2025` y para `verify_stack.sh`.
- El DAG pasa `year` como entero; el CLI lo recibe como texto (`--param year=2024`). Ambos se renderizan igual en las plantillas.
- Tipos de tabla: además de lo indicado en el spec, `bool` → `boolean`.
- CI: `dag-validate` reconstruye la imagen con `load: true` reutilizando la caché de GitHub Actions del job `build` (no comparte la imagen entre jobs). Los jobs que descargan de GHCR llevan `packages: read`.
- `rollback-prod` usa `environment: prod` para leer `PREV_IMAGE`, por lo que puede pedir aprobación del environment.
- Hook de ruff: `ruff-check` (el id `ruff` es un alias obsoleto).
- Checkov: justificaciones escritas con `checkov:skip` en la plantilla y el Dockerfile (HEALTHCHECK definido por servicio en compose).
- `make e2e` usa `.venv/bin/python` para los checks si existe; en CI se instala `pandas`.
