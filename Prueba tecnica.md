# Introduction
The goal of this technical test is to let you demonstrate your skills across the full life cycle of a modern data platform: first deploying it as code, then building on top of it. It combines two previously separate tests into a single exercise for the Cloud Data Engineer L2 profile, run by the Data Infrastructure and Data Technologies units at SDG Group.
The test has two parts. In **Part 1 - Infrastructure**, you show your architecture and infrastructure skills: automated deployment, infrastructure as code (IaC), component integration and knowledge of reference technologies. In **Part 2 - Data Engineering**, you implement an advanced metadata-driven framework in Python. Part 1 enables the platform and Part 2 develops on it. You then defend both parts in a single technical presentation.

# Part 1 - Infraestructure
- **Proposed steps**
    The Data Engineering team needs to deploy a data platform that is replicable, isolated by environment (dev and prod) and fully automated. Your goal is to develop the IaC code needed to bring up this ecosystem locally on Docker, treating the infrastructure as software: modular, secure and validated through a pipeline.
- **Stack requirements (per environment)**. The system must be able to instantiate the following components independently and in isolation for each environment:
    1. **Orchestrator (Apache Airflow)**. Official image, latest stable version, with AWS and Postgres providers included.
    2. **Object storage (Silo)**. Silo (pgsty/silo), a MinIO community fork compatible with S3, accessible by API and web console. Acts as source storage: contains the input files processed by Airflow.
    3. **Database (PostgreSQL)**. An instance that serves as the Airflow metadata database and the target database for the processed data.
- **Architecture constraints**:
    * **Zero-touch**: once the deployment is executed, the environment must be 100% operational. The connections between Airflow, Postgres and MinIO, as well as the initial storage structures, must be created automatically, with no manual configuration in the UIs.
    * **Persistence**: destroying the containers must not mean losing business data or the orchestrator’s history.
    * **Isolation**: Dev and Prod can coexist on the same machine without clashes of networks, volumes, ports, or credentials. The code is the same for both; only the configuration changes by environment.

- **Continuous Integration and Deployment (CI/CD)**
    Develop a pipeline configuration file (GitHub Actions, GitLab CI or similar) designed for this project's repository. Even though the final execution of the stack is local, the pipeline must reflect the team's infrastructure delivery strategy and answer two scenarios:
    1. **When a Pull Request is opened:** how do you ensure the quality, format and security of the IaC code before it reaches a main branch?
    2. **On merge:** how would you design the promotion and automated deployment strategy across environments?

    Note: the pipeline does not need to be executable against your local Docker, but we will evaluate its maturity, the validation tools you chose and the logic implemented.


# Part 2 - Data Engineering
- **Practical development - Metadata-driven framework**
    In this section, the points to be discussed are the following:
    1. Unzip the file assets.zip received along with this document.
    2. Develop a Python-based program that does the following. **Program description:** the program should, directed by the metadata file metadata.json, run a process that reads data from the described sources, executes the indicated transformations and writes the data to the specified destinations. It is important that the program can change its behavior dynamically via the proposed metadata and that it is not an ad hoc development.
    3. The code has to be compiled and executed using the CSV data2024.csv as input data.
    4. After the first run, you will be asked to run it again using the CSV data2025.csv. You must demonstrate the requested behavior in the outputs (overwrite, append and merge).
    5. In addition, 2 codes (completely apart from point 2) are requested to perform the following checks (e.g. a unit test):
    a. Which rows have changed from the 2024 file to the 2025 file.
    b. What data quality problems the 2025 file has (Both sexes != Men + Women).
    6. Build a DAG that runs the Python framework developed in the previous steps. The DAG must run on the Apache Airflow instance deployed in Part 1, using the same platform (Airflow, PostgreSQL and MinIO) rather than a separate deployment.

# Defense and technical presentation
You will prepare a short supporting presentation that covers both parts. With Part 1 you enable the infrastructure, and with Part 2 you develop on top of it. Regardless of how far you get, we will value your research skills and how you present your solution.
- **Part 1 - Infrastructure (enabling the platform)**
    * **Architecture diagram:** overview of the deployed components, their connectivity flows and how isolation between environments is managed.
    * **Justification of decisions:** why you structured or designed the IaC code the way you did.
    * **CI/CD and quality strategy:** explanation of the static analysis or security tools you decided to include in the pipeline.
    * **Improvement points:** if you had to migrate this local stack to a real production infrastructure on a public cloud (AWS/Azure/GCP), what architecture would you propose to guarantee high availability and real scalability?

- **Part 2 - Data Engineering (developing on the platform)**
    * **Framework design:** how the metadata (metadata.json) drives sources, transformations and destinations, and why it is not an ad hoc development.
    * **Demonstration of behaviors:** the outputs of the data2024.csv and data2025.csv runs showing overwrite, append and merge.
    * **Checks:** results of the two independent checks (rows changed between 2024 and 2025, and data quality problems where Both sexes != Men + Women).
    * **Orchestration:** the Airflow DAG running the framework on the platform enabled in Part 1.