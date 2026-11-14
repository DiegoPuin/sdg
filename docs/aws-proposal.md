# Propuesta de migración a AWS

## Etapa 1 — MWAA Serverless
- Pago por tarea; sin UI de Airflow; DAGs definidos en YAML; el cómputo arranca por tarea.
- Validar que el DAG (`check_input` + `run_dataflow` con el paquete `mdf`) se pueda ejecutar en Serverless: el paquete `mdf` debe estar disponible en el entorno de ejecución de las tareas.

## Etapa 2 — MWAA micro/small o ECS Fargate
Criterios de salto desde la etapa 1:
- Necesidad de la UI de Airflow.
- DAGs Python dinámicos u operadores no soportados.
- Horas-tarea × tarifa superior al coste fijo mensual.
- Tareas sensibles a latencia (el arranque por tarea añade segundos).
- Plugins propios.

## Punto de equilibrio
`horas-tarea al mes × tarifa Serverless` frente a `horas del mes × tarifa del entorno + workers adicionales`. Por debajo del punto de equilibrio compensa Serverless; por encima, el entorno fijo.

## UI de estado personalizada (solo propuesta, no se construye)
- EventBridge (origen `aws.airflow-serverless`) → Lambda → DynamoDB.
- Sondeo de reconciliación con `ListWorkflowRuns` / `GetWorkflowRun` para cubrir eventos perdidos.
- API Gateway + Lambda → front estático en S3/CloudFront. Autenticación con Cognito o IAM Identity Center. Solo lectura. Enlace a los logs de CloudWatch.
- Procesamiento idempotente por identificador de ejecución y de tarea.

## Equivalencias

| Local | AWS | Azure | GCP |
|---|---|---|---|
| Silo | S3 | Blob Storage / ADLS Gen2 | Cloud Storage |
| Postgres de metadata de Airflow | RDS / Aurora Multi-AZ | Azure Database for PostgreSQL | Cloud SQL / AlloyDB |
| Postgres warehouse | RDS / Aurora separada (Redshift a mayor escala) | PostgreSQL Flexible Server (Synapse a mayor escala) | Cloud SQL / AlloyDB (BigQuery a mayor escala) |
| Airflow en Docker | MWAA / ECS Fargate | Data Factory Managed Airflow / AKS | Cloud Composer |
| `.env` | Secrets Manager / SSM | Key Vault | Secret Manager |
| Imagen Docker | ECR | ACR | Artifact Registry |
| GitHub Actions → despliegue | OIDC → rol IAM | OIDC → federated credential | Workload Identity Federation |

## Seguridad
- Roles IAM por carga de trabajo, sin claves estáticas (ver `cloudformation/data-security.yaml`).
- Secrets Manager con rotación y secrets backend de Airflow para las conexiones.
- S3 con política de denegación sin TLS, SSE-KMS y endpoint VPC.
- RDS privada y cifrada, accesible solo desde el grupo de seguridad de la carga de trabajo.
- OIDC de GitHub hacia AWS (sin credenciales de larga duración en CI).
- Cuentas separadas para dev y prod.
- CloudTrail y GuardDuty activados.

## Costos
- Right-sizing y entornos pequeños en dev (`MultiAZ=false`, instancias `t4g`).
- VPC endpoints (S3, Secrets Manager) frente a NAT Gateway.
- Secrets Manager solo donde haya rotación; el resto en SSM Parameter Store.
- Ciclo de vida de S3 sobre `demo/output/historic/` (IA a 90 días, Glacier a 365).

## Alta disponibilidad y recuperación
- Multi-AZ dentro de una región (RDS/Aurora, MWAA).
- Backups con recuperación a un punto en el tiempo (PITR) y retención de 14 días en prod.
- Versionado de S3 para recuperar objetos sobrescritos.
- Multi-región (replicación S3 y réplica de lectura entre regiones) solo como mención.

## Límite de pandas
El procesamiento ocurre en memoria del worker. Cuando un fichero no quepa, el mismo metadata puede ejecutarse en tareas ECS de mayor tamaño o en Glue cambiando únicamente el motor de ejecución, sin tocar el metadata.

## Puntos de mejora reconocidos
- pandas frente a DuckDB/Spark a escala.
- El merge no detecta borrados.
- Cargas incrementales en lugar de ficheros completos.
- Validación de calidad previa a la carga (integrar el check B como tarea del DAG).
- Pool de Airflow cuando haya varios DAGs.
- Job de integración en todos los PR (hoy solo tras el merge).
- Runner self-hosted para desplegar de verdad (los jobs de despliegue son ilustrativos).
- Evolución de esquema en las tablas de destino.
