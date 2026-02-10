# SciDK Troubleshooting Guide

This guide provides solutions to common problems encountered when running SciDK. Each issue includes symptoms, diagnosis steps, and solutions.

## Table of Contents

- [Application Won't Start](#application-wont-start)
- [Neo4j Connection Issues](#neo4j-connection-issues)
- [Import and Scan Failures](#import-and-scan-failures)
- [Database Issues](#database-issues)
- [Performance Problems](#performance-problems)
- [Authentication and Permission Errors](#authentication-and-permission-errors)
- [Disk Space Issues](#disk-space-issues)
- [Network and Connectivity](#network-and-connectivity)

## Application Won't Start

### Problem: Port Already in Use

**Symptoms**:
```
Error: [Errno 98] Address already in use
OSError: [Errno 48] Address already in use
```

**Diagnosis**:
```bash
# Find what's using port 5000
sudo lsof -i :5000
sudo netstat -tlnp | grep 5000
```

**Solutions**:

1. **Kill the existing process**:
   ```bash
   # Find the PID
   sudo lsof -i :5000
   # Kill it
   sudo kill -9 <PID>
   ```

2. **Use a different port**:
   ```bash
   export SCIDK_PORT=5001
   scidk-serve
   ```

3. **Update systemd configuration**:
   ```bash
   sudo nano /etc/systemd/system/scidk.service
   # Change Environment="SCIDK_PORT=5000" to desired port
   sudo systemctl daemon-reload
   sudo systemctl restart scidk
   ```

### Problem: Python Module Not Found

**Symptoms**:
```
ModuleNotFoundError: No module named 'flask'
ModuleNotFoundError: No module named 'scidk'
```

**Diagnosis**:
```bash
# Check if virtual environment is activated
which python
# Should show: /path/to/.venv/bin/python

# Check installed packages
pip list | grep flask
```

**Solutions**:

1. **Activate virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

2. **Reinstall dependencies**:
   ```bash
   pip install -e .
   # Or with dev dependencies:
   pip install -e .[dev]
   ```

3. **Verify installation**:
   ```bash
   pip show scidk
   ```

### Problem: Permission Denied

**Symptoms**:
```
PermissionError: [Errno 13] Permission denied: '/opt/scidk/...'
```

**Diagnosis**:
```bash
# Check file ownership
ls -la /opt/scidk
ls -la ~/.scidk/db/
```

**Solutions**:

1. **Fix ownership** (if running as specific user):
   ```bash
   sudo chown -R scidk:scidk /opt/scidk
   sudo chown -R $USER:$USER ~/.scidk
   ```

2. **Fix permissions**:
   ```bash
   chmod 755 /opt/scidk
   chmod 644 /opt/scidk/*.py
   ```

3. **Run as correct user**:
   ```bash
   sudo -u scidk scidk-serve
   ```

## Neo4j Connection Issues

### Problem: Cannot Connect to Neo4j

**Symptoms**:
- "Failed to connect to Neo4j" error in UI or logs
- Commit to Graph fails
- Map page shows no data from Neo4j

**Diagnosis**:
```bash
# Check if Neo4j is running
docker compose -f docker-compose.neo4j.yml ps

# Check Neo4j logs
docker compose -f docker-compose.neo4j.yml logs neo4j | tail -50

# Test connection manually
curl http://localhost:7474
```

**Solutions**:

1. **Start Neo4j** (if not running):
   ```bash
   docker compose -f docker-compose.neo4j.yml up -d
   ```

2. **Check credentials**:
   - Navigate to Settings → Neo4j
   - Verify URI: `bolt://localhost:7687`
   - Verify username: `neo4j`
   - Enter correct password
   - Click "Test Connection"

3. **Check firewall**:
   ```bash
   # Allow port 7687 (Bolt) and 7474 (HTTP)
   sudo ufw allow 7687
   sudo ufw allow 7474
   ```

4. **Verify NEO4J_AUTH environment variable**:
   ```bash
   echo $NEO4J_AUTH
   # Should output: neo4j/your_password
   ```

5. **Reset Neo4j password**:
   ```bash
   ./scripts/neo4j_set_password.sh 'NewPassword123!' \
     --container scidk-neo4j \
     --current 'neo4jiscool'
   ```

### Problem: Authentication Failed

**Symptoms**:
```
The client is unauthorized due to authentication failure.
neo4j.exceptions.AuthError
```

**Diagnosis**:
```bash
# Check configured credentials
grep NEO4J_AUTH .env

# Check Neo4j is ready
docker compose -f docker-compose.neo4j.yml logs neo4j | grep "Started"
```

**Solutions**:

1. **Update password in Settings**:
   - Settings → Neo4j
   - Enter correct password
   - Click "Save"

2. **Verify password in Neo4j Browser**:
   - Navigate to http://localhost:7474
   - Log in with credentials
   - If login fails, password needs reset

3. **Reset to default password**:
   ```bash
   # Stop Neo4j
   docker compose -f docker-compose.neo4j.yml down -v

   # Set password
   export NEO4J_AUTH=neo4j/neo4jiscool

   # Start Neo4j
   docker compose -f docker-compose.neo4j.yml up -d
   ```

### Problem: Neo4j Connection Timeout

**Symptoms**:
- Long delays before connection errors
- Timeouts in logs

**Solutions**:

1. **Check network connectivity**:
   ```bash
   telnet localhost 7687
   # Or:
   nc -zv localhost 7687
   ```

2. **Increase timeout** (in Settings → Neo4j or environment):
   ```bash
   export NEO4J_TIMEOUT=30  # seconds
   ```

3. **Check Docker network**:
   ```bash
   docker network inspect bridge
   ```

## Import and Scan Failures

### Problem: Scan Fails with Permission Error

**Symptoms**:
- Scan shows "failed" status
- Log shows permission denied for files/directories

**Diagnosis**:
```bash
# Check directory permissions
ls -la /path/to/scan/directory

# Try listing manually
ls /path/to/scan/directory
```

**Solutions**:

1. **Fix permissions**:
   ```bash
   # Make directory readable
   chmod -R o+r /path/to/directory
   ```

2. **Run as correct user**:
   ```bash
   # If using systemd, update service user
   sudo nano /etc/systemd/system/scidk.service
   # Set User= to user with access
   ```

3. **Use different path with proper permissions**

### Problem: Large Files Cause Memory Errors

**Symptoms**:
- Application crashes during scan
- "Out of memory" errors
- System becomes unresponsive

**Solutions**:

1. **Increase batch size settings**:
   - Settings → Interpreters
   - Increase batch size to process fewer files at once

2. **Use selective scanning**:
   - Scan specific subdirectories instead of entire tree
   - Use non-recursive mode for large directories

3. **Increase available memory**:
   ```bash
   # For systemd service
   sudo nano /etc/systemd/system/scidk.service
   # Add: LimitMEMLOCK=8G
   ```

4. **Exclude large files**:
   - Use file extension filters
   - Filter by file size in UI

### Problem: Rclone Scan Fails

**Symptoms**:
- Rclone scans show error status
- "rclone not found" error
- Remote not configured error

**Diagnosis**:
```bash
# Check if rclone is installed
which rclone
rclone version

# List configured remotes
rclone listremotes

# Test remote connection
rclone lsd remote:
```

**Solutions**:

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
   # Follow prompts to set up your remote
   ```

3. **Test remote access**:
   ```bash
   rclone ls remote:bucket
   ```

4. **Enable rclone provider**:
   ```bash
   export SCIDK_PROVIDERS=local_fs,mounted_fs,rclone
   ```

### Problem: Import Creates Duplicate Nodes

**Symptoms**:
- Map shows duplicate File or Folder nodes
- Relationship counts don't match expected

**Diagnosis**:
```cypher
// In Neo4j Browser
MATCH (f:File)
WITH f.path as path, count(*) as cnt
WHERE cnt > 1
RETURN path, cnt
```

**Solutions**:

1. **Clean up duplicates**:
   ```cypher
   // Delete duplicate nodes (keep one)
   MATCH (f:File)
   WITH f.path as path, collect(f) as nodes
   WHERE size(nodes) > 1
   FOREACH (n IN tail(nodes) | DELETE n)
   ```

2. **Use data cleaning UI**:
   - Navigate to Files/Datasets
   - Use bulk delete to remove duplicates

3. **Re-scan and commit**:
   - Delete affected scan
   - Re-run scan
   - Commit to graph

## Database Issues

### Problem: Database is Locked

**Symptoms**:
```
sqlite3.OperationalError: database is locked
```

**Diagnosis**:
```bash
# Check for multiple processes
ps aux | grep scidk

# Check SQLite journal mode
sqlite3 ~/.scidk/db/files.db "PRAGMA journal_mode;"
```

**Solutions**:

1. **Enable WAL mode** (if not already enabled):
   ```bash
   sqlite3 ~/.scidk/db/files.db "PRAGMA journal_mode=WAL;"
   ```

2. **Kill duplicate processes**:
   ```bash
   # Find all scidk processes
   ps aux | grep scidk-serve
   # Kill extras (keep only one)
   kill <PID>
   ```

3. **Restart application**:
   ```bash
   sudo systemctl restart scidk
   ```

### Problem: Database Corruption

**Symptoms**:
```
sqlite3.DatabaseError: database disk image is malformed
PRAGMA integrity_check fails
```

**Diagnosis**:
```bash
# Check database integrity
sqlite3 ~/.scidk/db/files.db "PRAGMA integrity_check;"
```

**Solutions**:

1. **Restore from backup**:
   ```bash
   sudo systemctl stop scidk
   cp ~/.scidk/db/files.db.backup ~/.scidk/db/files.db
   sudo systemctl start scidk
   ```

2. **Attempt recovery** (if no backup):
   ```bash
   # Dump and rebuild
   sqlite3 ~/.scidk/db/files.db ".dump" > dump.sql
   sqlite3 ~/.scidk/db/files_new.db < dump.sql
   mv ~/.scidk/db/files.db ~/.scidk/db/files.db.corrupt
   mv ~/.scidk/db/files_new.db ~/.scidk/db/files.db
   ```

3. **Check disk for errors**:
   ```bash
   df -h
   sudo fsck /dev/sda1  # Adjust device as needed
   ```

### Problem: Migration Failures

**Symptoms**:
- Health endpoint reports old schema_version
- Application errors on startup about missing columns/tables

**Diagnosis**:
```bash
# Check migration status
curl http://localhost:5000/api/health | jq '.sqlite.schema_version'

# Check logs for migration errors
sudo journalctl -u scidk -n 100 | grep migration
```

**Solutions**:

1. **Manual migration** (advanced):
   ```bash
   # Backup first!
   cp ~/.scidk/db/files.db ~/.scidk/db/files.db.pre-migration

   # Run migrations manually via Python
   python3 -c "from scidk.core import migrations; migrations.migrate()"
   ```

2. **Restore and retry**:
   ```bash
   # Restore from working backup
   # Ensure latest code is pulled
   git pull
   pip install -e . --upgrade
   ```

## Performance Problems

### Problem: Slow Scan Performance

**Symptoms**:
- Scans take hours for moderate-sized directories
- UI becomes unresponsive during scans

**Diagnosis**:
```bash
# Check if ncdu/gdu is installed
which ncdu
which gdu

# Check system load
top
htop
```

**Solutions**:

1. **Install faster file enumeration tools**:
   ```bash
   # Ubuntu/Debian:
   sudo apt-get install ncdu

   # macOS:
   brew install ncdu gdu
   ```

2. **Use non-recursive scans**:
   - Uncheck "Recursive" in scan dialog
   - Scan specific subdirectories

3. **Enable fast_list mode** (for rclone):
   - Check "Fast List" option in scan dialog

4. **Adjust batch size**:
   - Settings → Interpreters
   - Reduce batch size for better responsiveness

### Problem: Map Page Slow to Load

**Symptoms**:
- Map takes minutes to render
- Browser becomes unresponsive

**Solutions**:

1. **Filter data**:
   - Use label type filters to reduce node count
   - Use relationship filters

2. **Use different layout**:
   - Try "breadthfirst" instead of "force"
   - Disable physics after initial layout

3. **Reduce node/edge styling**:
   - Decrease node size slider
   - Decrease edge width slider

4. **Limit data in graph**:
   - Use selective imports
   - Clean up old or unnecessary data

### Problem: Slow Database Queries

**Symptoms**:
- File browsing is slow
- Search takes long time

**Solutions**:

1. **Run VACUUM**:
   ```bash
   sqlite3 ~/.scidk/db/files.db "VACUUM;"
   ```

2. **Run ANALYZE**:
   ```bash
   sqlite3 ~/.scidk/db/files.db "ANALYZE;"
   ```

3. **Check database size**:
   ```bash
   du -sh ~/.scidk/db/files.db*
   # If very large, consider archiving old data
   ```

4. **Restart application**:
   ```bash
   sudo systemctl restart scidk
   ```

## Authentication and Permission Errors

### Problem: Cannot Log In

**Symptoms**:
- Login page shows "Invalid credentials"
- Correct password doesn't work

**Solutions**:

1. **Reset admin password** (via SQLite):
   ```python
   import bcrypt
   import sqlite3

   password = b'newpassword'
   hashed = bcrypt.hashpw(password, bcrypt.gensalt())

   conn = sqlite3.connect('/path/to/files.db')
   conn.execute("UPDATE users SET password_hash=? WHERE username='admin'", (hashed,))
   conn.commit()
   ```

2. **Check if authentication is enabled**:
   ```bash
   # Check Settings → Security in UI
   # Or query database:
   sqlite3 ~/.scidk/db/files.db "SELECT * FROM auth_config;"
   ```

3. **Disable authentication temporarily** (troubleshooting only):
   - Not recommended for production
   - Consult security team first

### Problem: Session Expires Too Quickly

**Symptoms**:
- Repeatedly redirected to login
- Session timeout message appears frequently

**Solutions**:

1. **Adjust session timeout**:
   - Settings → General
   - Increase "Session Timeout" value
   - Click "Save"

2. **Check for auto-lock settings**:
   - Settings → Security
   - Adjust inactivity timeout

### Problem: Unauthorized Access to API

**Symptoms**:
```
401 Unauthorized
403 Forbidden
```

**Solutions**:

1. **Include authentication header**:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:5000/api/endpoint
   ```

2. **Check user role**:
   - Admin role required for certain endpoints
   - Verify user has appropriate permissions

3. **Regenerate token** (if expired)

## Disk Space Issues

### Problem: Disk Full Errors

**Symptoms**:
```
OSError: [Errno 28] No space left on device
Disk space critical alert
```

**Diagnosis**:
```bash
# Check disk usage
df -h

# Find large files
du -sh ~/.scidk/db/* | sort -h
du -sh ./data/neo4j/* | sort -h

# Check log size
sudo journalctl --disk-usage
```

**Solutions**:

1. **Clean up old logs**:
   ```bash
   sudo journalctl --vacuum-time=30d
   sudo journalctl --vacuum-size=500M
   ```

2. **Remove old backups**:
   ```bash
   find ~/.scidk/backups -mtime +90 -delete
   ```

3. **Clean up old scans**:
   - Navigate to Files → Scans
   - Delete old or unnecessary scans

4. **VACUUM database**:
   ```bash
   sqlite3 ~/.scidk/db/files.db "VACUUM;"
   ```

5. **Expand storage**:
   - Add disk space to VM/server
   - Move data directory to larger partition

### Problem: Database File Growing Too Large

**Symptoms**:
- Database file is multiple GB
- Disk space alerts

**Diagnosis**:
```bash
du -sh ~/.scidk/db/files.db*

# Check table sizes
sqlite3 ~/.scidk/db/files.db "
SELECT name, SUM(pgsize) as size
FROM dbstat
GROUP BY name
ORDER BY size DESC;
"
```

**Solutions**:

1. **Archive old scans**:
   ```bash
   # Export old scans to files
   # Delete from database
   ```

2. **Run VACUUM**:
   ```bash
   sqlite3 ~/.scidk/db/files.db "VACUUM;"
   ```

3. **Clean up WAL files**:
   ```bash
   sqlite3 ~/.scidk/db/files.db "PRAGMA wal_checkpoint(TRUNCATE);"
   ```

## Network and Connectivity

### Problem: Cannot Access Web UI

**Symptoms**:
- Browser shows "Connection refused"
- "This site can't be reached"

**Diagnosis**:
```bash
# Check if application is running
sudo systemctl status scidk

# Check if port is open
netstat -tlnp | grep 5000

# Test locally
curl http://localhost:5000/api/health
```

**Solutions**:

1. **Start application**:
   ```bash
   sudo systemctl start scidk
   ```

2. **Check firewall**:
   ```bash
   sudo ufw status
   sudo ufw allow 5000
   ```

3. **Check nginx configuration** (if using reverse proxy):
   ```bash
   sudo nginx -t
   sudo systemctl status nginx
   ```

4. **Check host binding**:
   ```bash
   # Ensure SCIDK_HOST=0.0.0.0 to accept remote connections
   export SCIDK_HOST=0.0.0.0
   ```

### Problem: Slow Network Performance

**Symptoms**:
- Pages take long time to load
- API requests timeout

**Solutions**:

1. **Check network connectivity**:
   ```bash
   ping your-server
   traceroute your-server
   ```

2. **Check server load**:
   ```bash
   top
   htop
   ```

3. **Restart nginx** (if using):
   ```bash
   sudo systemctl restart nginx
   ```

4. **Check for rate limiting** (if configured)

## Log File Locations

- **Application logs** (systemd): `journalctl -u scidk`
- **nginx access logs**: `/var/log/nginx/access.log`
- **nginx error logs**: `/var/log/nginx/error.log`
- **Neo4j logs**: `docker compose -f docker-compose.neo4j.yml logs neo4j`
- **SQLite errors**: Application logs (journalctl)

## Getting More Help

If problems persist after trying these solutions:

1. **Gather diagnostic information**:
   ```bash
   # Health check
   curl http://localhost:5000/api/health > health.json

   # Recent logs
   sudo journalctl -u scidk -n 500 > scidk.log

   # System info
   uname -a > system.txt
   df -h >> system.txt
   free -h >> system.txt
   ```

2. **Check documentation**:
   - [DEPLOYMENT.md](DEPLOYMENT.md)
   - [OPERATIONS.md](OPERATIONS.md)
   - [SECURITY.md](SECURITY.md)

3. **Report issue**:
   - Include error messages
   - Include diagnostic output
   - Describe steps to reproduce
   - Mention environment (OS, Python version, etc.)
