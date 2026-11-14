"""DAG que ejecuta el framework mdf sobre el metadata del proyecto."""

import logging
from datetime import timedelta
from urllib.parse import quote

from airflow.sdk import BaseHook, Param, dag, get_current_context, task

log = logging.getLogger(__name__)

BUCKET = "data"
METADATA = "/opt/airflow/metadata/metadata.json"


@dag(
    dag_id="mdf_run",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["mdf"],
    params={"year": Param(2024, type="integer")},
)
def mdf_run():
    @task(retries=2, retry_delay=timedelta(seconds=30))
    def check_input() -> str:
        from airflow.providers.amazon.aws.hooks.s3 import S3Hook

        year = get_current_context()["params"]["year"]
        key = f"demo/input/data{year}.csv"
        if not S3Hook(aws_conn_id="silo_s3").check_for_key(key, bucket_name=BUCKET):
            raise FileNotFoundError(f"No existe el archivo de entrada: s3://{BUCKET}/{key}")
        log.info("Entrada encontrada: s3://%s/%s", BUCKET, key)
        return key

    @task(retries=0)
    def run_dataflow() -> list[dict]:
        from mdf.runner import Connections, run

        year = get_current_context()["params"]["year"]
        s3 = BaseHook.get_connection("silo_s3")
        pg = BaseHook.get_connection("warehouse_pg")
        dsn = f"postgresql://{quote(pg.login)}:{quote(pg.password)}@{pg.host}:{pg.port}/{pg.schema}"
        connections = Connections(
            s3_endpoint_url=s3.extra_dejson["endpoint_url"],
            s3_access_key=s3.login,
            s3_secret_key=s3.password,
            warehouse_dsn=dsn,
        )
        result = run(METADATA, {"year": year}, connections)
        for node in result.nodes:
            log.info("mdf %s", node)
        return [n for n in result.nodes if n["type"] in ("file", "table") and "rows" in n]

    check_input() >> run_dataflow()


mdf_run()
