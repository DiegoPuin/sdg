# SPEC — Plataforma de datos local + framework metadata-driven + CI/CD

Documento de construcción. Describe qué se construye. No contiene justificaciones.

---

## 0. Reglas para el agente que construye

1. Seguir este spec literalmente. Ante una ambigüedad, elegir la opción más simple coherente con el spec y anotarla en `README.md` (sección "Supuestos").
2. No modificar `metadata/metadata.json` (ver Apéndice A).
3. Los CSV reales (`data2024.csv`, `data2025.csv`) y el `metadata.json` original los aporta el usuario en `data/`. Si `metadata/metadata.json` no existe, crearlo con el contenido del Apéndice A.
4. Todo lo marcado como **[VERIFICAR]** depende de la versión pinneada: comprobarlo contra la documentación oficial o ejecutando el comando antes de darlo por bueno.
5. Construir por fases (sección 30). Al terminar cada fase: ejecutar sus comprobaciones y corregir antes de seguir.
6. Ningún secreto literal en el repositorio. Los `.env` reales están en `.gitignore`.
7. Versiones: fijar el **tag exacto de la última versión estable** de Airflow, Postgres, Silo y `mc` en el momento de construir. Prohibido `latest`. Se guardan en `env/versions.env` (sección 3).
8. Python 3.12. Texto del repositorio en español; identificadores de código en inglés.

---

## 1. Entregables

| # | Entregable | Ubicación |
|---|---|---|
| E1 | Stack Docker por entorno (dev, prod) | `compose.yaml`, `docker/`, `env/`, `connections/`, `scripts/`, `Makefile` |
| E2 | Framework Python `mdf` | `src/mdf/`, `pyproject.toml` |
| E3 | Check A: filas cambiadas 2024→2025 | `checks/diff_rows.py` |
| E4 | Check B: calidad de datos | `checks/dq_both_sexes.py` |
| E5 | DAG de Airflow | `dags/mdf_run.py` |
| E6 | Tests | `tests/` |
| E7 | Hook pre-commit y pipelines | `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `.github/workflows/cd.yml` |
| E8 | Plantilla CloudFormation (datos y seguridad) | `cloudformation/data-security.yaml` |
| E9 | Documentación | `README.md`, `docs/diagrams.md`, `docs/aws-proposal.md` |

## 2. Estructura del repositorio

```
.
├── compose.yaml
├── Makefile
├── pyproject.toml
├── README.md
├── .pre-commit-config.yaml
├── .gitignore  .dockerignore  .yamllint  .hadolint.yaml  .gitleaks.toml  ruff.toml
├── .github/
│   ├── workflows/{ci.yml,cd.yml}
│   ├── CODEOWNERS
│   └── dependabot.yml
├── docker/
│   ├── airflow/{Dockerfile,render_connections.py,init.sh}
│   ├── postgres/initdb/01-init.sh
│   └── silo/init.sh
├── env/
│   ├── versions.env
│   ├── .env.dev.example
│   └── .env.prod.example
├── connections/{silo_s3.json,warehouse_pg.json}
├── scripts/{gen_env.sh,verify_stack.sh}
├── data/                         # data2024.csv, data2025.csv (aportados por el usuario)
├── metadata/metadata.json        # sin modificar
├── src/mdf/
│   ├── __init__.py  cli.py  config.py  graph.py  params.py  context.py  registry.py  runner.py  storage.py
│   ├── expressions.py            # filter / add_fields / group
│   ├── readers/file_reader.py
│   ├── transformations/{filter.py,add_fields.py,group.py}
│   └── writers/{file_writer.py,table_writer.py}
├── checks/{diff_rows.py,dq_both_sexes.py}
├── dags/mdf_run.py
├── tests/{unit,e2e,fixtures}/
├── cloudformation/data-security.yaml
└── docs/{diagrams.md,aws-proposal.md}
```

---

## PARTE 1 — INFRAESTRUCTURA LOCAL

### 3. Configuración por entorno

- Un único `compose.yaml`. Todos los valores variables salen de variables de entorno.
- Selección de entorno: `ENV=dev|prod`. El Makefile ejecuta siempre:
  `docker compose --env-file env/versions.env --env-file env/.env.$(ENV) -p sdg-$(ENV) ...`
- Prohibido: `container_name`, `name:` fijo en redes o volúmenes.
- Anclas YAML (`x-airflow-common`) para la configuración compartida de los tres servicios de Airflow.

**`env/versions.env`** (versionado, sin secretos, compartido por ambos entornos):

```
AIRFLOW_VERSION=<tag exacto>
POSTGRES_IMAGE=postgres:<tag exacto>
SILO_IMAGE=docker.io/pgsty/silo:<RELEASE-tag exacto>
MC_IMAGE=docker.io/pgsty/mc:<tag exacto>
```

**`env/.env.<env>.example`** (versionado, placeholders) y **`env/.env.<env>`** (generado, `.gitignore`):

```
ENV_NAME=dev
COMPOSE_PROJECT_NAME=sdg-dev
AIRFLOW_IMAGE=sdg-airflow:local

PORT_AIRFLOW=8080
PORT_POSTGRES=5432
PORT_SILO_API=9000
PORT_SILO_CONSOLE=9001

POSTGRES_SUPERUSER=postgres
POSTGRES_SUPERPASS=<random>
AIRFLOW_DB_NAME=airflow
AIRFLOW_DB_USER=airflow
AIRFLOW_DB_PASS=<random>
WAREHOUSE_DB_NAME=warehouse
WAREHOUSE_DB_USER=warehouse_rw
WAREHOUSE_DB_PASS=<random>

SILO_ROOT_USER=<random>
SILO_ROOT_PASSWORD=<random>
SILO_APP_ACCESS_KEY=<random>
SILO_APP_SECRET_KEY=<random>
S3_ENDPOINT_URL=http://silo:9000

AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=<random>
AIRFLOW_FERNET_KEY=<generated>
AIRFLOW_JWT_SECRET=<random>

WAREHOUSE_DSN=postgresql://${WAREHOUSE_DB_USER}:${WAREHOUSE_DB_PASS}@postgres:5432/${WAREHOUSE_DB_NAME}
```

Valores de prod: `ENV_NAME=prod`, `COMPOSE_PROJECT_NAME=sdg-prod`, puertos `8081`, `5433`, `9100`, `9101`, y todos los secretos distintos de dev.

**`scripts/gen_env.sh ENV`:** genera `env/.env.<ENV>` desde el `.example` sustituyendo cada `<random>` por un valor aleatorio y `AIRFLOW_FERNET_KEY` por una Fernet key válida. No sobrescribe un archivo existente. Dev y prod nunca comparten secretos.

### 4. Servicios

Executor: `LocalExecutor`. Sin broker ni workers separados. Sin triggerer.

| Servicio | Imagen | Tipo | Depende de |
|---|---|---|---|
| `postgres` | `${POSTGRES_IMAGE}` | long-running | — |
| `silo` | `${SILO_IMAGE}` | long-running | — |
| `silo-init` | `${MC_IMAGE}` | one-shot | `silo` healthy |
| `airflow-init` | `${AIRFLOW_IMAGE}` | one-shot | `postgres` healthy |
| `airflow-apiserver` | `${AIRFLOW_IMAGE}` | long-running | `airflow-init` completed, `silo-init` completed |
| `airflow-scheduler` | `${AIRFLOW_IMAGE}` | long-running | `airflow-init` completed |
| `airflow-dag-processor` | `${AIRFLOW_IMAGE}` | long-running | `airflow-init` completed |

Reglas comunes:
- `depends_on` con `condition: service_healthy` (servicios) y `condition: service_completed_successfully` (one-shot).
- Servicios long-running: `restart: unless-stopped`.
- Todos los servicios: `security_opt: ["no-new-privileges:true"]`; usuario no root cuando la imagen lo permita.
- Puertos publicados solo en `127.0.0.1`: Airflow `${PORT_AIRFLOW}:8080`, Postgres `${PORT_POSTGRES}:5432`, Silo `${PORT_SILO_API}:9000` y `${PORT_SILO_CONSOLE}:9001`.
- Volúmenes con nombre: `pgdata` (`/var/lib/postgresql/data`), `silo-data` (`/data`), `airflow-logs` (`/opt/airflow/logs`).
- Variables de entorno `S3_ENDPOINT_URL`, `S3_ACCESS_KEY` (= `SILO_APP_ACCESS_KEY`), `S3_SECRET_KEY` (= `SILO_APP_SECRET_KEY`) y `WAREHOUSE_DSN` disponibles en los contenedores de Airflow para el CLI `mdf`.

### 5. Postgres

- Una sola instancia. `docker/postgres/initdb/01-init.sh` (se ejecuta solo con volumen vacío) crea de forma idempotente:
  - Roles `AIRFLOW_DB_USER` y `WAREHOUSE_DB_USER`.
  - BD `airflow` (owner `AIRFLOW_DB_USER`) y BD `warehouse` (owner `WAREHOUSE_DB_USER`).
  - Cada rol sin acceso a la BD del otro (`REVOKE CONNECT` a `PUBLIC` en ambas).
- Las tablas de destino (`demo`, `raw_demo`) viven en el esquema `public` de `warehouse`.
- Healthcheck: `pg_isready`.

### 6. Silo

- Comando: `server /data --console-address ":9001"`.
- Variables: `MINIO_ROOT_USER=${SILO_ROOT_USER}`, `MINIO_ROOT_PASSWORD=${SILO_ROOT_PASSWORD}`.
- Healthcheck en forma exec: `silo healthcheck ready` **[VERIFICAR]**.
- `docker/silo/init.sh` (servicio `silo-init`, `restart: "no"`), idempotente, con la imagen `mc` **[VERIFICAR sintaxis de `mc admin policy` y `mc admin user` en la versión pinneada]**:
  1. Alias con credenciales root.
  2. `mb --ignore-existing` del bucket **`data`**.
  3. Política `data-rw` con acceso de lectura y escritura solo a `arn:aws:s3:::data` y `arn:aws:s3:::data/*`.
  4. Usuario de servicio `SILO_APP_ACCESS_KEY` / `SILO_APP_SECRET_KEY` con la política `data-rw`.
  5. Copia de `./data/data2024.csv` (montado en solo lectura) a `data/demo/input/data2024.csv`.
- `data2025.csv` NO se carga automáticamente. Se sube a mano desde la consola web de Silo (se puede iniciar sesión con el usuario de servicio) **[VERIFICAR]**; el Makefile y el pipeline lo suben con `mc` (target `load-2025`).

Estructura de objetos:

```
data/demo/input/data2024.csv
data/demo/input/data2025.csv
data/demo/output/last/        # Parquet (overwrite)
data/demo/output/historic/    # Parquet particionado por load_date (append)
```

### 7. Airflow

**Dockerfile (`docker/airflow/Dockerfile`), multi-stage:**
- Etapa `build`: instala `build` y construye el wheel de `mdf` desde `pyproject.toml` y `src/`.
- Etapa final: `apache/airflow:${AIRFLOW_VERSION}-python3.12`; instala con el archivo de constraints oficial de esa versión `apache-airflow-providers-amazon`, `apache-airflow-providers-postgres` y el provider necesario para el auth manager elegido **[VERIFICAR]**; instala el wheel de `mdf` con sus dependencias.
- Copia `dags/` a `/opt/airflow/dags`, `metadata/` a `/opt/airflow/metadata`, `connections/` a `/opt/airflow/connections` y `docker/airflow/{render_connections.py,init.sh}` a `/opt/airflow/`.
- Build args: `AIRFLOW_VERSION`.
- No se monta código por bind-mount.

**Configuración común (`x-airflow-common`)** **[VERIFICAR cada variable contra la versión pinneada]**:

```
AIRFLOW__CORE__EXECUTOR=LocalExecutor
AIRFLOW__CORE__LOAD_EXAMPLES=False
AIRFLOW__CORE__FERNET_KEY=${AIRFLOW_FERNET_KEY}
AIRFLOW__API_AUTH__JWT_SECRET=${AIRFLOW_JWT_SECRET}
AIRFLOW__CORE__EXECUTION_API_SERVER_URL=http://airflow-apiserver:8080/execution/
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://${AIRFLOW_DB_USER}:${AIRFLOW_DB_PASS}@postgres:5432/${AIRFLOW_DB_NAME}
```

Auth manager: el que permita crear el usuario admin con `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` por línea de comandos (FAB) **[VERIFICAR]**.

**`airflow-init` (`init.sh`), idempotente:**
1. `airflow db migrate`.
2. Crear el usuario admin si no existe.
3. `python render_connections.py`: lee cada `connections/*.json`, expande variables de entorno con `os.path.expandvars` y deja el resultado en un archivo temporal.
4. Importar las conexiones con `airflow connections import ... --overwrite` **[VERIFICAR el flag; si no existe, borrar y recrear cada conexión]**. Se sobrescriben en cada `up`.

**Conexiones** (una por archivo en `connections/`; una conexión nueva = un archivo nuevo en un PR; nunca secretos literales):

`connections/silo_s3.json`
```json
{"silo_s3": {"conn_type": "aws", "login": "${SILO_APP_ACCESS_KEY}", "password": "${SILO_APP_SECRET_KEY}",
  "extra": {"endpoint_url": "${S3_ENDPOINT_URL}", "region_name": "us-east-1"}}}
```

`connections/warehouse_pg.json`
```json
{"warehouse_pg": {"conn_type": "postgres", "host": "postgres", "port": 5432,
  "schema": "${WAREHOUSE_DB_NAME}", "login": "${WAREHOUSE_DB_USER}", "password": "${WAREHOUSE_DB_PASS}"}}
```

Healthcheck de `airflow-apiserver`: HTTP al endpoint de salud de la API **[VERIFICAR ruta]**.

### 8. Script `scripts/verify_stack.sh ENV`

Falla (exit ≠ 0) con mensaje claro si alguna comprobación no se cumple. Comprueba:
1. Todos los servicios long-running en estado healthy.
2. La UI de Airflow responde en `127.0.0.1:${PORT_AIRFLOW}`.
3. Las conexiones `silo_s3` y `warehouse_pg` existen en Airflow (`airflow connections get`).
4. El bucket `data` existe y contiene `demo/input/data2024.csv`.
5. Las BD `airflow` y `warehouse` existen.
6. Imprime `VERIFY OK` al final.

### 9. Makefile

| Target | Acción |
|---|---|
| `make env ENV=dev` | `scripts/gen_env.sh` |
| `make build` | `docker build` de la imagen Airflow con `AIRFLOW_VERSION` de `env/versions.env`; tag `${AIRFLOW_IMAGE}` |
| `make up ENV=dev` | `docker compose ... up -d --wait` |
| `make down ENV=dev` | Elimina contenedores, conserva volúmenes |
| `make destroy ENV=dev` | `down -v` con confirmación (`FORCE=1` la omite) |
| `make verify ENV=dev` | `scripts/verify_stack.sh` |
| `make run ENV=dev YEAR=2024` | `docker compose exec airflow-scheduler mdf run --metadata /opt/airflow/metadata/metadata.json --param year=$(YEAR)` |
| `make load-2025 ENV=dev` | Sube `data/data2025.csv` a `data/demo/input/` con `mc` (contenedor one-shot en la red del proyecto, credenciales del usuario de servicio) |
| `make deploy ENV=dev AIRFLOW_IMAGE=<ref>` | `docker compose pull` + `up -d --wait` |
| `make test` | `pytest` con cobertura |
| `make lint` | `pre-commit run --all-files` |
| `make e2e ENV=dev` | `tests/e2e/run_e2e.sh` |
| `make logs ENV=dev` | `docker compose logs -f` |

---

## PARTE 2 — FRAMEWORK `mdf`

### 10. Paquete

- Dependencias: `pandas`, `pyarrow`, `fsspec`, `s3fs`, `psycopg[binary]`, `pydantic>=2`, `jinja2`.
- Extras de desarrollo: `pytest`, `pytest-cov`, `ruff`.
- `pyproject.toml`: backend de build estándar; entry point `mdf = mdf.cli:main`; configuración de `pytest` y `coverage` (fuente: `src/mdf` y `checks`).
- Versiones mínimas fijadas en `pyproject.toml` con rangos compatibles; sin versiones inexistentes.

**CLI**

```
mdf run      --metadata PATH [--dataflow NAME] [--param k=v ...]
mdf validate --metadata PATH [--param k=v ...]
```

Conexiones del CLI por variables de entorno: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `WAREHOUSE_DSN`.

**API de librería** (usada por el DAG):

```python
from mdf.runner import run, Connections
run(metadata_path: str, params: dict, connections: Connections, dataflow: str | None = None) -> RunResult
```

`Connections` es un dataclass con `s3_endpoint_url`, `s3_access_key`, `s3_secret_key`, `warehouse_dsn`.

**Códigos de salida:** 0 OK · 2 metadata inválida · 3 error de lectura · 4 error de transformación · 5 error de escritura.

**Logging:** una línea JSON por nodo ejecutado con `run_id`, `dataflow`, `node`, `type`, `rows`, `duration_ms`. Para outputs `table` en modo `merge` añade `rows_inserted`, `rows_updated`, `rows_unchanged`.

### 11. Lectura del metadata y validación

El metadata tiene el formato del Apéndice A. Vocabulario soportado:

| Sección | `type` | Campos |
|---|---|---|
| `inputs[]` | `file` | `name`, `config.path`, `config.format` ∈ {`csv`,`parquet`}, `options` (opcional), `waits` (opcional, lista de nombres de outputs) |
| `transformations[]` | `filter` | `name`, `input`, `config.filter` |
| | `add_fields` | `name`, `input`, `config.fields[]` con `name` y `expression` |
| | `group` | `name`, `input`, `config.group_fields[]`, `config.aggregations[]` |
| `outputs[]` | `file` | `name`, `input`, `config.path`, `config.format` = `parquet`, `config.save_mode` ∈ {`overwrite`,`append`}, `config.partition` (opcional) |
| | `table` | `name`, `input`, `config.table`, `config.save_mode` ∈ {`merge`,`append`,`overwrite`}, `config.primary_key` (obligatorio si `merge`) |

Validación (modelos pydantic en `config.py`, antes de cualquier lectura o escritura; error → exit 2 con mensaje claro):
- Nombres de nodo únicos en todo el dataflow.
- `input` de cada transformación y output referencia un nodo existente.
- `waits` referencia outputs existentes.
- Sin ciclos.
- `save_mode` válido por tipo; `primary_key` presente si `merge`.
- `type` y `format` registrados.

### 12. Grafo de ejecución (`graph.py`)

- Nodos: inputs, transformations, outputs.
- Aristas: `input` → nodo; `waits` → arista desde cada output indicado hacia el input que espera.
- Ejecución en orden topológico. El orden del JSON no es el orden de ejecución (en el metadata, `filter_rows` aparece antes que `new_fields`).
- Los resultados intermedios se guardan en un diccionario `nombre → DataFrame` durante la ejecución.
- Un input con `waits` se lee solo después de completarse los outputs indicados.

### 13. Parámetros y rutas

- Plantillas: todas las cadenas del metadata se renderizan con Jinja2 usando `StrictUndefined` (un parámetro ausente es error → exit 2). Parámetro del enunciado: `year`.
- `current_date()` y similares NO son plantillas Jinja: son funciones de expresión (sección 14).
- Resolución de rutas (`storage.py`): una ruta `/<bucket>/<clave...>` del metadata se resuelve a `s3://<bucket>/<clave...>`. Ejemplo: `/data/demo/input/data2024.csv` → `s3://data/demo/input/data2024.csv`.
- Acceso mediante `fsspec`/`s3fs` con `endpoint_url`, clave y secreto de `Connections`.
- Modo de almacenamiento alternativo `local` (raíz configurable) para tests unitarios, sin cambiar el código de lectores y escritores.

### 14. Lectura y expresiones (pandas)

**Reader `file`:**
- `csv`: `pandas.read_csv` con codificación `utf-8-sig` por defecto (el CSV tiene BOM) y con `keep_default_na=False, na_values=[""]` (el texto `N/A` de `municipality` debe conservarse como texto; con los valores por defecto de pandas se convertiría en nulo y el filtro del metadata no eliminaría esas filas). Mapeo de `options`: `header: "true"` → `header=0` (`"false"` → `None`), `delimiter` → `sep`, `thousands` → `thousands`. Cualquier opción no soportada → exit 2.
- `parquet`: lee el directorio completo como dataset.

**`filter`:** `DataFrame.query(config.filter)`.

**`add_fields`:** por cada campo, en orden:
1. Literal entre comillas simples o dobles (`'demography'`) → columna constante de ese texto.
2. Literal numérico → columna constante.
3. Función registrada: `current_date()` → `datetime.date.today()`; `current_timestamp()` → `datetime.datetime.now()`.
4. Cualquier otra expresión → `DataFrame.eval`.
Las funciones se registran en un diccionario extensible en `expressions.py`.

**`group`:** `DataFrame.groupby(group_fields, as_index=False)`. Cada agregación debe cumplir `^\s*(\w+)\(\s*(\w+)\s*\)\s+as\s+(\w+)\s*$` con función ∈ {`sum`,`count`,`min`,`max`,`avg`}; `avg` se traduce a `mean`. Una agregación no soportada → exit 2.

### 15. Escritura

**Output `file` (Parquet como directorio de ficheros):**
- Escribe ficheros `part-<uuid>.parquet` dentro del directorio indicado por `config.path`.
- Con `partition`: subdirectorios estilo hive `<col>=<valor>/`.
- `overwrite`: elimina todo el contenido del directorio y escribe.
- `append`: añade ficheros nuevos sin tocar los existentes.
- Los outputs `file` no son atómicos.

**Output `table` (Postgres):**
- Una transacción por output; ante error, `ROLLBACK` y exit 5.
- Crea la tabla si no existe con tipos derivados del DataFrame: entero → `bigint`, decimal → `double precision`, fecha → `date`, timestamp → `timestamp`, resto → `text`.
- `append`: carga el DataFrame en una tabla temporal con `COPY` e inserta en el destino.
- `overwrite`: `TRUNCATE` del destino e inserción desde la temporal.
- `merge`:
  1. Si la tabla es nueva, crea `PRIMARY KEY (primary_key...)`; si existe, comprueba que hay una restricción única sobre esas columnas.
  2. Valida antes de escribir que `primary_key` es única en el DataFrame (duplicados → exit 5 con mensaje).
  3. Carga en tabla temporal con `COPY`.
  4. Calcula `rows_inserted` (claves que no existen en destino), `rows_updated` (existen y algún valor difiere) y `rows_unchanged`.
  5. Aplica `INSERT ... ON CONFLICT (primary_key) DO UPDATE SET <columnas no clave> = EXCLUDED.<columna> WHERE (<columnas destino>) IS DISTINCT FROM (<columnas EXCLUDED>)`.
- Separar la generación de SQL (funciones puras, testeables sin base de datos) de su ejecución.

### 16. Orden de ejecución y resultados esperados con los datos reales

Con `year=2024` y luego `year=2025` sobre el mismo entorno:

| Salida | Tras 2024 | Tras 2025 |
|---|---|---|
| `write_last_file` (Parquet, overwrite) | 15.410 filas | 15.410 filas |
| `write_historic_file` (Parquet, append, partición `load_date`) | 15.410 | 30.820 |
| `write_delta_merge` → tabla `demo` | 15.410 | 15.410; log: 0 insertadas, 5 actualizadas, 15.405 sin cambio |
| `write_delta_raw` → tabla `raw_demo` | 15.410 | 30.820 |

Columnas de `demo` y `raw_demo`: `province`, `municipality`, `sex`, `total_population`.
Ejecutar dos veces el mismo año duplica filas en los outputs `append` (comportamiento documentado, sin protección).

---

## PARTE 3 — CHECKS INDEPENDIENTES

No importan `mdf`. Leen CSV locales con `pandas`: separador `;`, miles con `.`, codificación `utf-8-sig`, `dtype=str`, `keep_default_na=False` (para que `N/A` se conserve como texto y no se pierdan grupos al agrupar o fusionar). Los valores de `total` se convierten a número después de leer, quitando el separador de miles; lo que no se convierta se clasifica como `NON_NUMERIC` y lo vacío como `NULL_VALUE`. Clave: `(province, municipality, sex)`.

### 17. `checks/diff_rows.py`

```
python checks/diff_rows.py --old PATH --new PATH [--out DIR]
```

- Compara los archivos completos (incluye `Both sexes` y filas con `municipality = N/A`).
- Outer merge por clave con indicador de origen; compara `total` como entero.
- Categorías: `added` (solo en `--new`), `removed` (solo en `--old`), `changed` (en ambos con `total` distinto).
- Consola: resumen con los tres conteos y tabla de las filas cambiadas (clave, valor anterior, valor nuevo).
- CSV en `--out` (por defecto `./out`): `added.csv`, `removed.csv`, `changed.csv`.
- Exit 0; exit 2 ante error de ejecución (archivo ausente, columnas ausentes).
- Resultado esperado con los datos reales: 0 añadidas, 0 eliminadas, **8 cambiadas**:

| province | municipality | sex | 2024 | 2025 |
|---|---|---|---|---|
| 02 Albacete | 02003 Albacete | Men | 1932 | 1935 |
| 02 Albacete | 02003 Albacete | Women | 1895 | 1890 |
| 33 Asturias | 33056 Ribadesella | Both sexes | 1439 | 1440 |
| 33 Asturias | 33056 Ribadesella | Men | 659 | 660 |
| 33 Asturias | 33068 Somiedo | Both sexes | 517 | 520 |
| 33 Asturias | 33068 Somiedo | Men | 247 | 250 |
| 42 Soria | 42097 Gormaz | Both sexes | 18 | 12 |
| 42 Soria | 42097 Gormaz | Men | 9 | 5 |

### 18. `checks/dq_both_sexes.py`

```
python checks/dq_both_sexes.py --file PATH [--out DIR] [--tolerance 0]
```

- Agrupa por `(province, municipality)` (incluye los grupos `N/A`) y pivota `sex` en columnas `Both sexes`, `Men`, `Women`.
- Regla: `Both sexes == Men + Women` con `abs(diferencia) <= tolerance`.
- Categorías de problema (`issue_type`):
  - `RULE_VIOLATION`: incumple la regla; incluye `delta = Both sexes − (Men + Women)`.
  - `NULL_VALUE`: valor vacío en alguno de los tres sexos.
  - `NON_NUMERIC`: valor no convertible a número.
  - `INCOMPLETE_GROUP`: falta alguno de los tres valores de `sex` en el grupo.
- Consola: resumen por categoría y tabla de problemas. CSV en `--out`: `dq_violations.csv` (grupo, `Both sexes`, `Men`, `Women`, `delta`, `issue_type`).
- Última línea de la consola: `STATUS: OK` o `STATUS: PENDING_REVIEW`.
- Exit 0 si OK; **1** si `PENDING_REVIEW`; **2** ante error de ejecución.
- Resultado esperado: `data2024.csv` → `STATUS: OK`. `data2025.csv` → `STATUS: PENDING_REVIEW` con 2 `RULE_VIOLATION`:

| province | municipality | Both sexes | Men | Women | delta |
|---|---|---|---|---|---|
| 02 Albacete | 02003 Albacete | 3827 | 1935 | 1890 | +2 |
| 42 Soria | 42097 Gormaz | 12 | 5 | 9 | −2 |

---

## PARTE 4 — DAG

### 19. `dags/mdf_run.py`

- API de Airflow 3: `from airflow.sdk import dag, task` y `Param` **[VERIFICAR imports contra la versión pinneada]**.
- `dag_id="mdf_run"`, `schedule=None`, `catchup=False`, `max_active_runs=1`, tags `["mdf"]`.
- `params={"year": Param(2024, type="integer")}`.
- Sin pools.

| Tarea | Detalle |
|---|---|
| `check_input` | `retries=2`, `retry_delay` 30 s. Con `S3Hook(aws_conn_id="silo_s3")` comprueba que existe la clave `demo/input/data{{ params.year }}.csv` en el bucket `data`. Falla con mensaje que incluye la ruta si no existe. |
| `run_dataflow` | `retries=0`. Lee las conexiones Airflow `silo_s3` y `warehouse_pg`, construye `mdf.runner.Connections` y llama `mdf.runner.run("/opt/airflow/metadata/metadata.json", {"year": year}, connections)`. Registra en el log de la tarea los conteos de cada output (incluidos `rows_inserted`, `rows_updated`, `rows_unchanged` del merge). Un exit/excepción del framework marca la tarea como fallida. |

Dependencia: `check_input >> run_dataflow`.

---

## PARTE 5 — PRUEBAS

### 20. Unitarias (`tests/unit/`, sin servicios externos)

| Área | Casos |
|---|---|
| Validación del metadata | Nombres duplicados; referencia inexistente en `input` y en `waits`; ciclo; `merge` sin `primary_key`; `save_mode` inválido; `type` desconocido |
| Grafo | Orden topológico del metadata real: `demo_data` < `new_fields` < `filter_rows` < `write_last_file` < `parquet_data` < `group_by_fields` < `write_delta_merge` y `write_delta_raw`; `waits` respetado |
| Parámetros | `{{ year }}` renderizado; parámetro ausente → error |
| Rutas | `/data/demo/input/data2024.csv` → `s3://data/demo/input/data2024.csv` |
| Reader | CSV con BOM, `;`, `thousands='.'` (`9.625` → 9625); `N/A` se conserva como texto y no como nulo; opción no soportada → error |
| Expresiones | `filter` sobre datos de ejemplo; `add_fields` con literal y `current_date()`; `group` con `sum(total) as total_population`; agregación no soportada → error |
| Writer de ficheros | `overwrite` y `append` en modo `local`; partición `load_date`; relectura del directorio |
| Writer de tablas | Generación de SQL para `append`, `overwrite` y `merge` (funciones puras); validación de clave duplicada |
| Check A | Fixtures con filas añadidas, eliminadas, cambiadas y sin cambios |
| Check B | Fixtures con total correcto, `RULE_VIOLATION`, `NULL_VALUE`, `NON_NUMERIC`, `INCOMPLETE_GROUP`; códigos de salida 0 y 1 |

Cobertura: `--cov=src/mdf --cov=checks --cov-fail-under=80`. Las funciones que solo ejecutan SQL contra Postgres se cubren en E2E y se marcan con `# pragma: no cover` únicamente en esas funciones.

### 21. E2E (`tests/e2e/run_e2e.sh ENV`)

Falla si cualquier aserción falla. Siempre ejecuta `make destroy FORCE=1` al terminar (aunque falle) y, si falló, guarda los logs de los contenedores en `e2e-logs/`. Los conteos de tablas se obtienen con `psql` dentro del contenedor `postgres`; los conteos de Parquet con un script Python ejecutado dentro del contenedor de Airflow (lee el directorio con `pandas`/`s3fs`). El script respeta una variable `AIRFLOW_IMAGE` exportada en el entorno del shell (tiene prioridad sobre el valor del `.env`).

En las rutas siguientes, cada `make` lleva `ENV=<ENV>` (el argumento del script).

**Ruta A (CLI), stack limpio:**
1. `make env up verify`.
2. `make run YEAR=2024`; comprobar con `psql` en `warehouse`: `demo` = 15.410 y `raw_demo` = 15.410; y Parquet de `last` = 15.410 filas.
3. `make load-2025`; `make run YEAR=2025`; comprobar: `demo` = 15.410, `raw_demo` = 30.820, `historic` = 30.820 filas, `last` = 15.410 filas; el log del merge contiene `rows_updated: 5`.
4. `make destroy FORCE=1`.

**Ruta B (DAG), stack limpio:**
1. `make up verify`.
2. Disparar `mdf_run` con `{"year": 2024}` y esperar `success` (tiempo máximo 300 s). Mismas aserciones que la ruta A paso 2.
3. `make load-2025`; disparar con `{"year": 2025}`; mismas aserciones que la ruta A paso 3.

**Checks:** ejecutar `diff_rows.py` y `dq_both_sexes.py` sobre `data/`; comprobar 8 cambiadas, `STATUS: OK` para 2024 y `STATUS: PENDING_REVIEW` (exit 1) para 2025.

---

## PARTE 6 — CI/CD (GitHub Actions)

### 22. `.pre-commit-config.yaml`

Hooks: `ruff` (lint y formato), `yamllint`, `hadolint`, `shellcheck`, `gitleaks`, `cfn-lint` (sobre `cloudformation/`). Versiones (`rev`) fijadas. El job de lint de CI ejecuta exactamente `pre-commit run --all-files`.

### 23. `ci.yml` — disparador `pull_request` hacia `main`

Configuración global: `permissions: contents: read`; `concurrency` por rama con cancelación; todas las actions fijadas por SHA de commit **[VERIFICAR SHA vigentes]**; Python 3.12.

| Job | Contenido | `needs` |
|---|---|---|
| `lint` | `pre-commit run --all-files` | — |
| `compose-validate` | `docker compose --env-file env/versions.env --env-file env/.env.dev.example config -q` y lo mismo con `.env.prod.example` | — |
| `iac-security` | `checkov` con frameworks `dockerfile`, `cloudformation`, `github_actions`; `cfn-lint cloudformation/*.yaml` | — |
| `deps-audit` | `pip-audit` sobre las dependencias del proyecto | — |
| `test` | `pytest` con cobertura y `--cov-fail-under=80` | — |
| `build` | `docker buildx build` (sin push, caché de GitHub Actions) y `trivy image` con fallo ante vulnerabilidades HIGH/CRITICAL con corrección disponible | `lint`, `compose-validate`, `iac-security`, `deps-audit`, `test` |
| `dag-validate` | Ejecutar en la imagen construida `airflow dags list-import-errors`; falla si hay errores | `build` |

Branch protection de `main` (documentada en el README): todos los jobs son required checks; sin push directo; al menos 1 aprobación.
Este pipeline NO levanta el stack.

### 24. `cd.yml` — disparador `push` a `main`

| Job | Contenido | `needs` |
|---|---|---|
| `build-publish` | Construye la imagen una sola vez; tag `sha-<commit>`; la publica en GHCR (`ghcr.io/<owner>/<repo>/airflow`); exporta el digest | — |
| `integration` | Exporta `AIRFLOW_IMAGE=<ref por digest>` (la imagen publicada) y ejecuta `tests/e2e/run_e2e.sh dev` (rutas A y B) | `build-publish` |
| `deploy-dev` | `environment: dev`; `make deploy ENV=dev AIRFLOW_IMAGE=<ref por digest>`; `make verify ENV=dev` | `integration` |
| `deploy-prod` | `environment: prod` (revisores requeridos); mismo digest; `make deploy ENV=prod`; `make verify ENV=prod` | `deploy-dev` |
| `rollback-prod` | Condición `needs.deploy-prod.result == 'failure'`: redespliega la imagen anterior guardada en la variable de environment `PREV_IMAGE`; `make verify` | `deploy-prod` |

Reglas:
- `deploy-dev`, `deploy-prod` y `rollback-prod`: `runs-on: [self-hosted, local-docker]` y `if: vars.ENABLE_DEPLOY == 'true'` (por defecto desactivados; ilustrativos).
- `concurrency: group: deploy-<env>` con `cancel-in-progress: false`.
- Tras un despliegue correcto de prod, actualizar `PREV_IMAGE` con el digest desplegado.
- Se despliega siempre por digest, solo tras pasar `integration`.
- Permisos del job `build-publish`: `packages: write`; el resto, `contents: read`.

### 25. Otros archivos

- `dependabot.yml`: ecosistemas `github-actions`, `docker`, `pip`; frecuencia semanal.
- `CODEOWNERS`: `* @<owner>`.

---

## PARTE 7 — AWS Y DOCUMENTACIÓN

### 26. `cloudformation/data-security.yaml`

Plantilla de datos y seguridad. No se despliega; se valida con `cfn-lint` y `checkov` (corregir hallazgos o añadir `checkov:skip` con motivo escrito).

Parámetros: `Environment` (`dev`|`prod`), `VpcId`, `PrivateSubnetIds` (lista), `AllowedSecurityGroupId`, `DBInstanceClass`, `MultiAZ` (`true`|`false`).

Recursos:
- `AWS::KMS::Key` para el cifrado de S3 y del secreto.
- `AWS::S3::Bucket` `data-<Environment>-<AccountId>`: cifrado SSE-KMS, versionado, `PublicAccessBlockConfiguration` completo, regla de ciclo de vida sobre el prefijo `demo/output/historic/` y registro de acceso desactivado salvo bucket de logs parametrizado.
- `AWS::S3::BucketPolicy`: denegar tráfico sin TLS.
- `AWS::IAM::Role` de carga de trabajo de Airflow: permisos de lectura y escritura solo sobre el bucket y lectura del secreto de la base de datos. Sin claves estáticas.
- `AWS::SecretsManager::Secret` con contraseña generada para la base de datos del warehouse.
- `AWS::RDS::DBSubnetGroup`, `AWS::EC2::SecurityGroup` (entrada solo desde `AllowedSecurityGroupId` al puerto 5432) y `AWS::RDS::DBInstance` PostgreSQL: privada (`PubliclyAccessible: false`), cifrada, `MultiAZ` por parámetro, retención de backups, `DeletionProtection` en prod.

Salidas: ARN del bucket, ARN del rol, ARN del secreto, endpoint de la base de datos.

### 27. `docs/diagrams.md`

Cuatro diagramas en Mermaid:
1. Arquitectura local: servicios, contenedores de inicialización, flujo de datos y coexistencia dev/prod (proyecto, puertos, volúmenes).
2. Grafo del dataflow `access-test`: inputs, transformaciones, outputs y la dependencia `waits`.
3. CI/CD: pipeline de PR y flujo posterior al merge (build, integración, dev, aprobación, prod, rollback).
4. Propuesta AWS por etapas, incluida la UI de estado.

### 28. `docs/aws-proposal.md`

Contenido:
- **Etapa 1:** MWAA Serverless (pago por tarea); sin UI de Airflow; DAGs en YAML; arranque de cómputo por tarea. Validar que el DAG (`check_input` + `run_dataflow` con el paquete `mdf`) pueda ejecutarse en Serverless.
- **Etapa 2:** MWAA micro/small o ECS Fargate. Criterios de salto: necesidad de la UI de Airflow, DAGs Python dinámicos u operadores no soportados, horas-tarea × tarifa superior al coste fijo mensual, tareas sensibles a latencia, plugins propios.
- **Punto de equilibrio:** horas-tarea al mes × tarifa de Serverless frente a horas del mes × tarifa del entorno + workers adicionales.
- **UI de estado personalizada (solo propuesta, no se construye):** EventBridge (origen `aws.airflow-serverless`) → Lambda → DynamoDB; sondeo de reconciliación con `ListWorkflowRuns`/`GetWorkflowRun`; API Gateway + Lambda → front estático en S3/CloudFront; autenticación con Cognito o IAM Identity Center; solo lectura; enlace a logs de CloudWatch; procesamiento idempotente por identificador de ejecución y de tarea.
- **Equivalencias:** Silo → S3; Postgres de metadata → RDS/Aurora Multi-AZ; warehouse → RDS/Aurora separada (Redshift a mayor escala); `.env` → Secrets Manager/SSM; imagen → ECR; más tabla Azure y GCP.
- **Seguridad:** roles IAM por carga de trabajo sin claves estáticas; Secrets Manager con rotación y secrets backend de Airflow para conexiones; S3 con política, SSE-KMS y endpoint VPC; RDS privada y cifrada; OIDC de GitHub hacia AWS; cuentas separadas dev/prod; CloudTrail y GuardDuty.
- **Costos:** right-sizing, entornos pequeños en dev, VPC endpoints frente a NAT, Secrets Manager solo con rotación, ciclo de vida de S3 para `historic`.
- **HA y recuperación:** Multi-AZ en una región, backups con recuperación a un punto en el tiempo, versionado de S3, multi-región como mención.
- **Límite de pandas:** memoria del worker; evolución a tareas ECS o Glue sin cambiar el metadata.
- **Puntos de mejora reconocidos:** pandas frente a DuckDB/Spark a escala; el merge no detecta borrados; cargas incrementales; validación de calidad previa a la carga; pool de Airflow con varios DAGs; job de integración en todos los PR; runner self-hosted para desplegar de verdad; evolución de esquema.

### 29. `README.md`

Secciones: requisitos; arranque rápido (`make env up verify`); tabla de puertos por entorno; cómo ejecutar el framework (`make run`); cómo subir `data2025.csv` (consola de Silo o `make load-2025`); cómo ejecutar el DAG; cómo ejecutar los checks; guion de demo; protección de rama; decisiones principales; supuestos; enlaces a `docs/`.

**Guion de demo (documentado en el README):**

| Paso | Entorno | Acción |
|---|---|---|
| 1 | dev | `make env up verify ENV=dev`; abrir la UI de Airflow y mostrar las conexiones |
| 2 | dev | `make run ENV=dev YEAR=2024`; mostrar 15.410 filas en `last`, `historic`, `demo`, `raw_demo` |
| 3 | dev | Subir `data2025.csv` a mano en la consola de Silo; `make run ENV=dev YEAR=2025`; mostrar los conteos de la sección 16 y el log del merge |
| 4 | prod | `make env up verify ENV=prod`; mismo recorrido con el DAG `mdf_run` desde la UI (`year` 2024 y luego 2025) |
| 5 | local | Ejecutar los checks A y B |
| 6 | dev | `make down` y `make up`: los datos persisten |
| 7 | GitHub | Mostrar `ci.yml` y `cd.yml` |

---

## 30. Fases de construcción

| Fase | Contenido | Comprobación para pasar |
|---|---|---|
| 0 | Repositorio, `versions.env` con las versiones exactas, `.gitignore`, `pyproject.toml` | `pip install -e .` sin errores |
| 1 | Infraestructura (secciones 3 a 9) | `make env up verify` en dev y en prod a la vez; AC-01 a AC-06 |
| 2 | Framework (secciones 10 a 16) con sus tests unitarios | `pytest` verde; `mdf validate` sobre `metadata/metadata.json` correcto |
| 3 | Checks (17 y 18) con tests | Resultados esperados con los datos reales |
| 4 | DAG (19) | `airflow dags list-import-errors` vacío; ejecución exitosa con 2024 |
| 5 | E2E (21) | `make e2e ENV=dev` verde |
| 6 | Pre-commit, `ci.yml`, `cd.yml` (22 a 25) | `pre-commit run --all-files` verde; `actionlint` sobre los workflows sin errores |
| 7 | CloudFormation y documentación (26 a 29) | `cfn-lint` y `checkov` sin hallazgos sin justificar |
| 8 | Verificación final | Todos los criterios de aceptación de la sección 31 |

## 31. Criterios de aceptación

| ID | Criterio | Verificación |
|---|---|---|
| AC-01 | `make env up verify ENV=dev` deja el stack operativo sin pasos manuales | `VERIFY OK` |
| AC-02 | Dev y prod corren a la vez sin conflictos | `docker ps` muestra los dos proyectos; los 4 puertos de cada uno responden |
| AC-03 | Las conexiones `silo_s3` y `warehouse_pg` son visibles en la UI de Airflow (Admin → Connections) | Inspección en la UI |
| AC-04 | Persistencia: `make down` + `make up` conserva tablas, objetos e historial de DAG | Conteos antes y después |
| AC-05 | Credenciales y puertos distintos entre dev y prod | Comparación de `env/.env.dev` y `env/.env.prod` |
| AC-06 | Versiones fijadas con tag exacto; ninguna `latest` | `grep` en `env/versions.env`, Dockerfile y `compose.yaml` |
| AC-07 | `mdf validate` rechaza metadata con ciclo, referencia inexistente, nombre duplicado y `merge` sin `primary_key` (exit 2) | Tests unitarios |
| AC-08 | Run 2024: `demo` y `raw_demo` con 15.410 filas; Parquet `last` e `historic` con 15.410 filas | `psql` y lectura de Parquet |
| AC-09 | Run 2025: `last` 15.410, `historic` 30.820, `demo` 15.410, `raw_demo` 30.820 | Ídem |
| AC-10 | El log del merge de 2025 informa 0 insertadas, 5 actualizadas, 15.405 sin cambio | Log del CLI y de la tarea |
| AC-11 | Check A sobre los datos reales: 0 añadidas, 0 eliminadas, 8 cambiadas | Consola y CSV |
| AC-12 | Check B: 2024 → `STATUS: OK`; 2025 → `STATUS: PENDING_REVIEW` con 2 `RULE_VIOLATION` (Albacete +2, Gormaz −2) y exit 1 | Consola, CSV y código de salida |
| AC-13 | El DAG `mdf_run` aparece en la UI y termina en `success` con `year` 2024 y 2025 | UI de Airflow |
| AC-14 | `check_input` falla con mensaje claro si no existe el archivo del año indicado | Disparo con `year` inexistente |
| AC-15 | Cobertura de tests ≥ 80 % | `make test` |
| AC-16 | `pre-commit run --all-files` sin errores | Local y CI |
| AC-17 | `ci.yml` bloquea un PR con secreto, Dockerfile inválido o test roto | Revisión de la definición de jobs y `needs` |
| AC-18 | `cd.yml` construye una vez, ejecuta integración, despliega por digest y exige aprobación para prod | Revisión de la definición de jobs |
| AC-19 | `cfn-lint` y `checkov` sobre `cloudformation/data-security.yaml` sin hallazgos sin justificar | Ejecución local |

---

## Apéndice A — `metadata/metadata.json` (sin modificar)

```json
{
  "dataflows": [
    {
      "name": "access-test",
      "inputs": [
        {
          "name": "demo_data",
          "type": "file",
          "config": { "path": "/data/demo/input/data{{ year }}.csv", "format": "csv" },
          "options": { "header": "true", "delimiter": ";", "thousands": "." }
        },
        {
          "name": "parquet_data",
          "type": "file",
          "config": { "path": "/data/demo/output/last", "format": "parquet" },
          "waits": ["write_last_file"]
        }
      ],
      "transformations": [
        {
          "name": "filter_rows",
          "type": "filter",
          "input": "new_fields",
          "config": { "filter": "sex != 'Both sexes' and municipality != 'N/A'" }
        },
        {
          "name": "new_fields",
          "type": "add_fields",
          "input": "demo_data",
          "config": {
            "fields": [
              { "name": "domain", "expression": "'demography'" },
              { "name": "load_date", "expression": "current_date()" }
            ]
          }
        },
        {
          "name": "group_by_fields",
          "type": "group",
          "input": "parquet_data",
          "config": {
            "group_fields": ["province", "municipality", "sex"],
            "aggregations": ["sum(total) as total_population"]
          }
        }
      ],
      "outputs": [
        {
          "name": "write_last_file",
          "type": "file",
          "input": "filter_rows",
          "config": { "path": "/data/demo/output/last", "format": "parquet", "save_mode": "overwrite" }
        },
        {
          "name": "write_historic_file",
          "type": "file",
          "input": "filter_rows",
          "config": {
            "path": "/data/demo/output/historic",
            "format": "parquet",
            "save_mode": "append",
            "partition": "load_date"
          }
        },
        {
          "name": "write_delta_merge",
          "type": "table",
          "input": "group_by_fields",
          "config": {
            "table": "demo",
            "save_mode": "merge",
            "primary_key": ["province", "municipality", "sex"]
          }
        },
        {
          "name": "write_delta_raw",
          "type": "table",
          "input": "group_by_fields",
          "config": { "table": "raw_demo", "save_mode": "append" }
        }
      ]
    }
  ]
}
```

## Apéndice B — Datos de los CSV (para tests y aserciones)

| Dato | Valor |
|---|---|
| Formato | `;` como separador, `.` como miles, UTF-8 con BOM, CRLF |
| Columnas | `province`, `municipality`, `sex`, `total` |
| Filas | 23.268 por archivo |
| Valores de `sex` | `Both sexes`, `Men`, `Women` |
| Provincias | 51 |
| Filas con `municipality = N/A` | 153 (3 por provincia) |
| Municipios reales | 7.705 |
| Clave `(province, municipality, sex)` | única; mismo conjunto de claves en 2024 y 2025 |
| Filas tras el filtro del metadata | 15.410 (7.705 municipios × `Men` y `Women`) |
| Filas que cambian de 2024 a 2025 | 8 (5 sobreviven al filtro; las otras 3 son `Both sexes`) |
| `Both sexes != Men + Women` | 0 filas en 2024; 2 grupos en 2025 |
