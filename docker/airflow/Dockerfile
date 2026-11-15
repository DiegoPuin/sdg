ARG AIRFLOW_VERSION

FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

# checkov:skip=CKV_DOCKER_2: el healthcheck de cada servicio (apiserver, scheduler, dag-processor) se define en compose.yaml
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12
ARG AIRFLOW_VERSION
USER 0
# Parches de seguridad de Debian disponibles (zlib).
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade zlib1g zlib1g-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
USER 50000:0
COPY --from=build /dist/*.whl /tmp/wheels/
RUN pip install --no-cache-dir \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt" \
      apache-airflow-providers-amazon \
      apache-airflow-providers-postgres \
      apache-airflow-providers-fab \
      /tmp/wheels/*.whl
# Correcciones de seguridad por encima del archivo de constraints (se valida con pip check y el e2e).
RUN pip install --no-cache-dir \
      "urllib3>=2.8.0" "aiohttp>=3.14.4" "msgpack>=1.2.3" "dnspython>=2.9.2" \
      "setuptools>=78.1.1" "soupsieve>=4.0.0" "pip>=26.3" \
    && pip check
COPY dags/ /opt/airflow/dags/
COPY metadata/ /opt/airflow/metadata/
COPY connections/ /opt/airflow/connections/
COPY docker/airflow/render_connections.py docker/airflow/init.sh /opt/airflow/
USER 50000:0
