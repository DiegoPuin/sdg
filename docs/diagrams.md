# Diagramas

## 1. Arquitectura local

Cada entorno es un proyecto Compose independiente (`sdg-dev`, `sdg-prod`): red, volúmenes, puertos y credenciales propios. El código y el `compose.yaml` son los mismos.

```mermaid
flowchart LR
  subgraph host["Host (127.0.0.1)"]
    subgraph dev["Proyecto sdg-dev — puertos 8080 / 5432 / 9000 / 9001"]
      direction LR
      sinit["silo-init (one-shot)"] -->|"mb, política data-rw, usuario, data2024.csv"| silo[("silo — bucket data")]
      pg[("postgres: airflow + warehouse")]
      ainit["airflow-init (one-shot)"] -->|"db migrate, admin, conexiones"| pg
      api["airflow-apiserver"] --> pg
      sch["airflow-scheduler (LocalExecutor)"] --> pg
      dagp["airflow-dag-processor"] --> pg
      sch -->|"mdf run / DAG mdf_run"| silo
      sch -->|"tablas demo / raw_demo"| pg
      vol1[["pgdata · silo-data · airflow-logs"]]
    end
    subgraph prod["Proyecto sdg-prod — puertos 8081 / 5433 / 9100 / 9101"]
      direction LR
      p2["Mismos servicios, volúmenes y red propios, secretos distintos"]
    end
  end
  user(("Usuario")) -->|"UI Airflow · consola Silo · make"| dev
  user --> prod
```

## 2. Grafo del dataflow `access-test`

```mermaid
flowchart TD
  demo_data["demo_data (input csv)"] --> new_fields["new_fields (add_fields)"]
  new_fields --> filter_rows["filter_rows (filter)"]
  filter_rows --> write_last_file["write_last_file (parquet, overwrite)"]
  filter_rows --> write_historic_file["write_historic_file (parquet, append, partición load_date)"]
  write_last_file -. "waits" .-> parquet_data["parquet_data (input parquet)"]
  parquet_data --> group_by_fields["group_by_fields (group)"]
  group_by_fields --> write_delta_merge["write_delta_merge (tabla demo, merge)"]
  group_by_fields --> write_delta_raw["write_delta_raw (tabla raw_demo, append)"]
```

## 3. CI/CD

```mermaid
flowchart TD
  subgraph PR["Pull request → main (ci.yml)"]
    lint & cv["compose-validate"] & iac["iac-security"] & deps["deps-audit"] & test --> build["build + trivy"] --> dagv["dag-validate"]
  end
  subgraph Merge["Push a main (cd.yml)"]
    bp["build-publish (GHCR, digest)"] --> integ["integration (e2e rutas A y B)"] --> dd["deploy-dev"] --> appr{{"aprobación del environment prod"}} --> dp["deploy-prod"]
    dp -->|"éxito"| prev["actualiza PREV_IMAGE"]
    dp -->|"fallo"| rb["rollback-prod (PREV_IMAGE)"]
  end
  PR -->|"merge"| Merge
```

## 4. Propuesta AWS por etapas

```mermaid
flowchart LR
  gh["GitHub Actions (OIDC)"] --> ecr[("ECR")]
  subgraph E1["Etapa 1 — MWAA Serverless"]
    mwaa["Workflows YAML: check_input + run_dataflow (mdf)"]
  end
  subgraph E2["Etapa 2 — MWAA micro/small o ECS Fargate"]
    mwaa2["Airflow gestionado / tareas Fargate"]
  end
  ecr --> mwaa
  mwaa -.->|"criterios de salto"| mwaa2
  mwaa --> s3[("S3 data (SSE-KMS)")]
  mwaa --> rds[("RDS / Aurora warehouse Multi-AZ")]
  mwaa --> sm["Secrets Manager"]
  mwaa -->|"eventos aws.airflow-serverless"| eb["EventBridge"] --> lam["Lambda"] --> ddb[("DynamoDB")]
  rec["Lambda de reconciliación (ListWorkflowRuns / GetWorkflowRun)"] --> ddb
  ddb --> apigw["API Gateway + Lambda (solo lectura)"] --> ui["Front estático S3 + CloudFront (Cognito / IAM Identity Center)"]
  mwaa --> cw["CloudWatch Logs"]
  ui -.->|"enlace a logs"| cw
```
