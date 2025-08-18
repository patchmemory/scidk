# Deployment Guide: Neo4j alongside SciDK

This document describes how to run Neo4j alongside the SciDK application. We standardize on Neo4j 5.x LTS as the knowledge graph backend. Choose Docker Compose for container-friendly environments, or Singularity for HPC contexts.

## Prerequisites
- Docker Engine and Docker Compose v2, or
- Singularity/Apptainer (for HPC) with network access enabled by your cluster policy.

## Environment Variables
Set these variables for the SciDK app and Neo4j connectivity:
- NEO4J_URI: bolt://localhost:7687 (or bolt+s://host:7687 for TLS)
- NEO4J_USER: neo4j
- NEO4J_PASSWORD: <strong-password>
- NEO4J_DB: neo4j (default)

Optional Neo4j tuning (set in compose or Singularity environment):
- NEO4J_server_memory_heap_initial__size: 2G
- NEO4J_server_memory_heap_max__size: 4G
- NEO4J_dbms_security_auth__enabled: "true"

## Option A: Docker Compose
A minimal compose file is provided at docker-compose.neo4j.yml. Example usage:

```
# Start Neo4j in the background
docker compose -f docker-compose.neo4j.yml up -d

# Inspect logs
docker compose -f docker-compose.neo4j.yml logs -f neo4j

# Stop
docker compose -f docker-compose.neo4j.yml down
```

Volumes:
- ./data/neo4j/data → /data
- ./data/neo4j/logs → /logs
- ./data/neo4j/plugins → /plugins

Ports:
- 7474 (HTTP)
- 7687 (Bolt)

Notes:
- APOC and neosemantics (n10s) are enabled by default via NEO4JLABS_PLUGINS in docker-compose.neo4j.yml.
- For production, prefer bolt+s with certificates and restrict exposure via firewall or docker network.

### Verify APOC and n10s (Docker)
Use cypher-shell:
```
# APOC version
cypher-shell -u neo4j -p <pass> "RETURN apoc.version() AS apoc_version;"

# List a few APOC procedures
cypher-shell -u neo4j -p <pass> "CALL dbms.procedures() YIELD name WHERE name STARTS WITH 'apoc.' RETURN name LIMIT 5;"

# Initialize n10s config (first time)
cypher-shell -u neo4j -p <pass> "CALL n10s.graphconfig.init();"

# Check n10s procedures
cypher-shell -u neo4j -p <pass> "CALL dbms.procedures() YIELD name WHERE name STARTS WITH 'n10s.' RETURN name LIMIT 5;"
```

## Option B: Singularity/Apptainer
A minimal definition file is provided at singularity/neo4j.def. Example usage (paths and ports may vary by cluster policy):

```
# Build the SIF from the definition file
sudo singularity build neo4j.sif singularity/neo4j.def

# Run Neo4j (bind a writable directory for /data and expose ports)
singularity exec \
  --bind $PWD/data/neo4j:/data \
  --bind $PWD/data/neo4j/logs:/logs \
  --env NEO4J_AUTH=neo4j/strongpassword \
  --env NEO4J_dbms_default__listen__address=0.0.0.0 \
  --env NEO4J_dbms_connector_bolt_listen__address=:7687 \
  --env NEO4J_dbms_connector_http_listen__address=:7474 \
  neo4j.sif \
  neo4j start
```

Plugins: The Singularity definition exports NEO4JLABS_PLUGINS='["apoc","n10s"]' and enables APOC file import/export and unrestricted procedures for apoc.* and n10s.*.

### Verify APOC and n10s (Singularity)
If cypher-shell is available inside the image, use the same commands as Docker, or run them via Neo4j Browser at http://host:7474.

## Application Configuration
Point SciDK to Neo4j via environment variables or a config file:
- NEO4J_URI=bolt://localhost:7687
- NEO4J_USER=neo4j
- NEO4J_PASSWORD=strongpassword

Future: When the SciDK Flask app is added, it should read these from environment or config/settings.yaml.

## Backup & Maintenance (brief)
- Backups: use neo4j-admin database dump/load or file-level backups when Neo4j is offline.
- Monitoring: review /logs; consider enabling metrics (Prometheus) in advanced setups.

## Security Notes
- Always set a strong NEO4J_PASSWORD.
- Restrict exposed ports to trusted networks.
- For TLS, use bolt+s and configure certificates per Neo4j docs.

## Setting/Changing the Neo4j Password
You have three common options:

1) Before first start (recommended)
- Set NEO4J_AUTH in your env or .env: NEO4J_AUTH=neo4j/<your-strong-password>
- Then start Neo4j: docker compose -f docker-compose.neo4j.yml up -d
- This sets the initial password and avoids the first-login force-change flow.

2) Via helper script (running instance)
- Use the provided script (works with Docker container or local cypher-shell):
```
# If running in Docker with container name scidk-neo4j
scripts/neo4j_set_password.sh 'NewPass123!' --container scidk-neo4j --current 'OldPass!'

# If running locally with cypher-shell
scripts/neo4j_set_password.sh 'NewPass123!' --host bolt://localhost:7687 --user neo4j --current 'OldPass!'
```

3) Directly with cypher-shell
```
cypher-shell -u neo4j -p 'OldPass!' -a bolt://localhost:7687 "ALTER CURRENT USER SET PASSWORD FROM 'OldPass!' TO 'NewPass123!';"
```

Notes:
- The scripts/init_env.sh and scripts/init_env.fish help manage NEO4J_AUTH and NEO4J_PASSWORD for both the app and Docker Compose.
- If you change the password after first start, remember to update your .env and restart any dependent services.
