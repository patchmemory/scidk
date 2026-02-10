# SciDK Deployment Guide

This guide covers production deployment of SciDK, including installation, configuration, and common deployment scenarios.

## Prerequisites

### System Requirements

- **OS**: Linux (Ubuntu 20.04+, RHEL 8+, or compatible), macOS 11+, or Windows 10+ with WSL2
- **Python**: 3.10 or higher
- **Memory**: Minimum 2GB RAM, 4GB+ recommended for large datasets
- **Disk**: 10GB+ free space for application and data storage
- **Neo4j** (optional): 5.x or higher for graph database functionality

### Required Software

1. **Python 3.10+** with pip and venv
2. **Neo4j** (optional but recommended): For persistent graph storage
3. **rclone** (optional): For cloud storage provider integration
4. **ncdu or gdu** (optional): For faster filesystem scanning

### Network Requirements

- Default port: 5000 (Flask application)
- Neo4j Bolt: 7687 (if using Neo4j)
- Neo4j HTTP: 7474 (Neo4j Browser UI)

## Installation

### Standard Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-org/scidk.git
   cd scidk
   ```

2. **Create virtual environment**:
   ```bash
   python3 -m venv .venv

   # Activate (bash/zsh):
   source .venv/bin/activate

   # Activate (fish):
   source .venv/bin/activate.fish
   ```

3. **Install dependencies**:
   ```bash
   # Production installation:
   pip install -e .

   # Or with development dependencies:
   pip install -e .[dev]
   ```

4. **Initialize environment**:
   ```bash
   # bash/zsh:
   source scripts/init_env.sh

   # Optional: create .env file
   source scripts/init_env.sh --write-dotenv
   ```

5. **Verify installation**:
   ```bash
   scidk-serve --help
   ```

### Docker Deployment (Neo4j)

SciDK includes Docker Compose configuration for Neo4j:

1. **Set Neo4j password** (recommended):
   ```bash
   export NEO4J_AUTH=neo4j/your_secure_password
   ```

2. **Start Neo4j**:
   ```bash
   docker compose -f docker-compose.neo4j.yml up -d
   ```

3. **Verify Neo4j is running**:
   ```bash
   docker compose -f docker-compose.neo4j.yml ps
   ```

   Access Neo4j Browser at http://localhost:7474

## Configuration

### Environment Variables

Create a `.env` file in the project root or set environment variables:

```bash
# Application
SCIDK_HOST=0.0.0.0
SCIDK_PORT=5000
SCIDK_CHANNEL=stable  # stable, beta, or dev

# Database
SCIDK_DB_PATH=~/.scidk/db/files.db
SCIDK_STATE_BACKEND=sqlite  # sqlite or memory

# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_AUTH=neo4j/your_password
SCIDK_NEO4J_DATABASE=neo4j

# Providers
SCIDK_PROVIDERS=local_fs,mounted_fs,rclone

# Logging
SCIDK_LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

### Neo4j Setup

1. **Using Docker** (recommended):
   ```bash
   export NEO4J_AUTH=neo4j/neo4jiscool
   docker compose -f docker-compose.neo4j.yml up -d
   ```

2. **Using existing Neo4j instance**:
   - Set `NEO4J_URI` to your Neo4j Bolt endpoint
   - Set `NEO4J_AUTH` to `username/password`
   - Ensure firewall allows connection to port 7687

3. **Configure in SciDK**:
   - Start SciDK: `scidk-serve`
   - Navigate to Settings → Neo4j
   - Enter URI, username, password, and database name
   - Click "Test Connection" to verify
   - Click "Save" to persist settings

### Rclone Configuration (Optional)

For cloud storage integration:

1. **Install rclone**:
   ```bash
   # Ubuntu/Debian:
   sudo apt-get install rclone

   # macOS:
   brew install rclone
   ```

2. **Configure remote**:
   ```bash
   rclone config
   ```

3. **Verify remote**:
   ```bash
   rclone listremotes
   ```

4. **Enable in SciDK**:
   ```bash
   export SCIDK_PROVIDERS=local_fs,mounted_fs,rclone
   ```

## systemd Service Setup (Linux)

For production deployments, run SciDK as a systemd service:

1. **Create service file** `/etc/systemd/system/scidk.service`:
   ```ini
   [Unit]
   Description=SciDK Scientific Data Knowledge System
   After=network.target neo4j.service
   Wants=neo4j.service

   [Service]
   Type=simple
   User=scidk
   Group=scidk
   WorkingDirectory=/opt/scidk
   Environment="PATH=/opt/scidk/.venv/bin"
   Environment="SCIDK_HOST=0.0.0.0"
   Environment="SCIDK_PORT=5000"
   Environment="NEO4J_URI=bolt://localhost:7687"
   Environment="NEO4J_AUTH=neo4j/your_password"
   ExecStart=/opt/scidk/.venv/bin/scidk-serve
   Restart=on-failure
   RestartSec=10
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```

2. **Create dedicated user**:
   ```bash
   sudo useradd -r -s /bin/false -d /opt/scidk scidk
   ```

3. **Set permissions**:
   ```bash
   sudo chown -R scidk:scidk /opt/scidk
   sudo chmod 750 /opt/scidk
   ```

4. **Enable and start service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable scidk
   sudo systemctl start scidk
   ```

5. **Check status**:
   ```bash
   sudo systemctl status scidk
   sudo journalctl -u scidk -f
   ```

## Reverse Proxy Setup (nginx)

For production, use nginx as a reverse proxy:

1. **Install nginx**:
   ```bash
   sudo apt-get install nginx
   ```

2. **Create nginx configuration** `/etc/nginx/sites-available/scidk`:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       # Redirect HTTP to HTTPS
       return 301 https://$server_name$request_uri;
   }

   server {
       listen 443 ssl http2;
       server_name your-domain.com;

       ssl_certificate /etc/ssl/certs/scidk.crt;
       ssl_certificate_key /etc/ssl/private/scidk.key;

       client_max_body_size 100M;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;

           # WebSocket support (if needed)
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }
   }
   ```

3. **Enable site**:
   ```bash
   sudo ln -s /etc/nginx/sites-available/scidk /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

## SSL/TLS Configuration

For HTTPS support using Let's Encrypt:

1. **Install certbot**:
   ```bash
   sudo apt-get install certbot python3-certbot-nginx
   ```

2. **Obtain certificate**:
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```

3. **Auto-renewal** (certbot sets this up automatically):
   ```bash
   sudo systemctl status certbot.timer
   ```

## Port Configuration

### Changing Default Port

1. **Via environment variable**:
   ```bash
   export SCIDK_PORT=8080
   scidk-serve
   ```

2. **Via .env file**:
   ```bash
   echo "SCIDK_PORT=8080" >> .env
   ```

3. **Via systemd** (edit `/etc/systemd/system/scidk.service`):
   ```ini
   Environment="SCIDK_PORT=8080"
   ```

## Common Deployment Issues

### Port Already in Use

**Symptom**: Error "Address already in use" when starting SciDK

**Solution**:
```bash
# Find process using port 5000
sudo lsof -i :5000
# or
sudo netstat -tlnp | grep 5000

# Kill the process or change SCIDK_PORT
export SCIDK_PORT=5001
scidk-serve
```

### Neo4j Connection Failed

**Symptom**: "Failed to connect to Neo4j" in logs or UI

**Diagnosis**:
```bash
# Check Neo4j is running
docker compose -f docker-compose.neo4j.yml ps

# Check Neo4j logs
docker compose -f docker-compose.neo4j.yml logs neo4j

# Test connection manually
curl http://localhost:7474
```

**Solutions**:
- Verify Neo4j is running: `docker compose -f docker-compose.neo4j.yml up -d`
- Check credentials match in Settings → Neo4j
- Verify firewall allows port 7687
- Check NEO4J_AUTH environment variable

### Permission Denied Errors

**Symptom**: Permission errors when accessing data directories

**Solution**:
```bash
# Ensure correct ownership
sudo chown -R scidk:scidk /opt/scidk
sudo chown -R scidk:scidk ~/.scidk

# Check directory permissions
ls -la /opt/scidk
chmod 750 /opt/scidk
```

### Out of Memory Errors

**Symptom**: Application crashes with memory errors on large scans

**Solutions**:
- Increase available RAM (4GB+ recommended)
- Use pagination for large datasets
- Enable batch processing in settings
- Use selective scanning instead of full recursive scans

### Database Locked Errors

**Symptom**: "Database is locked" errors in SQLite

**Solutions**:
```bash
# Check WAL mode is enabled (should happen automatically)
sqlite3 ~/.scidk/db/files.db "PRAGMA journal_mode;"

# Should return: wal
# If not, enable it:
sqlite3 ~/.scidk/db/files.db "PRAGMA journal_mode=WAL;"
```

## Upgrading SciDK

### Standard Upgrade

1. **Backup configuration**:
   ```bash
   # Via UI: Settings → Export Settings
   # Or manually:
   cp ~/.scidk/db/files.db ~/.scidk/db/files.db.backup
   ```

2. **Pull latest code**:
   ```bash
   cd /opt/scidk
   git pull origin main
   ```

3. **Update dependencies**:
   ```bash
   source .venv/bin/activate
   pip install -e . --upgrade
   ```

4. **Restart service**:
   ```bash
   sudo systemctl restart scidk
   ```

5. **Verify**:
   ```bash
   curl http://localhost:5000/api/health
   ```

### Database Migrations

SciDK automatically runs database migrations on startup. Check migration status:

```bash
curl http://localhost:5000/api/health | jq '.sqlite'
```

## Health Checks

### Application Health

```bash
curl http://localhost:5000/api/health
```

Expected response includes:
- SQLite connection status
- Journal mode (should be "wal")
- Schema version
- Neo4j connection status (if configured)

### Graph Health

```bash
curl http://localhost:5000/api/health/graph
```

Returns Neo4j connection status and node/relationship counts.

## Backup and Restore

See [OPERATIONS.md](OPERATIONS.md) for detailed backup and restore procedures.

## Security Considerations

See [SECURITY.md](SECURITY.md) for comprehensive security best practices.

## Support

- **Documentation**: Check docs/ directory for detailed guides
- **Issues**: Report bugs on GitHub issue tracker
- **Logs**: Check systemd journal or application logs for errors

## Next Steps

- Review [OPERATIONS.md](OPERATIONS.md) for day-to-day operational procedures
- Review [SECURITY.md](SECURITY.md) for security hardening
- Review [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions
