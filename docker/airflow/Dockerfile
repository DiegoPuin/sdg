ARG AIRFLOW_VERSION

FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

# checkov:skip=CKV_DOCKER_2: el healthcheck de cada servicio (apiserver, scheduler, dag-processor) se define en compose.yaml
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12
ARG AIRFLOW_VERSION
COPY --from=build /dist/*.whl /tmp/wheels/
RUN pip install --no-cache-dir \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt" \
      apache-airflow-providers-amazon \
      apache-airflow-providers-postgres \
      apache-airflow-providers-fab \
      /tmp/wheels/*.whl
COPY dags/ /opt/airflow/dags/
COPY metadata/ /opt/airflow/metadata/
COPY connections/ /opt/airflow/connections/
COPY docker/airflow/render_connections.py docker/airflow/init.sh /opt/airflow/
USER 50000:0
