# SciDK Operations Manual

This manual covers day-to-day operations, monitoring, maintenance, and operational workflows for production SciDK deployments.

## Daily Operations

### Starting the Application

**Via systemd** (production):
```bash
sudo systemctl start scidk
sudo systemctl status scidk
```

**Via command line** (development):
```bash
cd /opt/scidk
source .venv/bin/activate
scidk-serve
```

**Verify startup**:
```bash
curl http://localhost:5000/api/health
```

### Stopping the Application

**Via systemd**:
```bash
sudo systemctl stop scidk
```

**Via command line**:
- Press `Ctrl+C` in the terminal running scidk-serve

### Restarting After Configuration Changes

```bash
sudo systemctl restart scidk
sudo journalctl -u scidk -f  # Monitor logs
```

## Monitoring System Health

### Health Check Endpoints

**Application Health**:
```bash
curl http://localhost:5000/api/health
```

Returns:
- SQLite database status and configuration
- Journal mode (should be "wal")
- Schema version
- Database connectivity

**Graph Health**:
```bash
curl http://localhost:5000/api/health/graph
```

Returns:
- Neo4j connection status
- Node counts by label
- Relationship counts by type
- Database statistics

### Key Metrics to Monitor

1. **Disk Space**:
   ```bash
   df -h ~/.scidk/db/
   df -h /var/lib/neo4j/  # Or your Neo4j data directory
   ```

2. **Memory Usage**:
   ```bash
   # Application memory
   ps aux | grep scidk-serve

   # Neo4j memory (if using Docker)
   docker stats scidk-neo4j
   ```

3. **Database Size**:
   ```bash
   du -sh ~/.scidk/db/files.db*
   ```

4. **Log File Size**:
   ```bash
   sudo journalctl --disk-usage
   du -sh /var/log/nginx/  # If using nginx
   ```

### Viewing Logs

**Application logs** (systemd):
```bash
# Real-time logs
sudo journalctl -u scidk -f

# Last 100 lines
sudo journalctl -u scidk -n 100

# Logs from specific time
sudo journalctl -u scidk --since "2024-01-01 00:00:00"

# Errors only
sudo journalctl -u scidk -p err
```

**Neo4j logs** (Docker):
```bash
docker compose -f docker-compose.neo4j.yml logs -f neo4j
```

**nginx logs**:
```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

## Backup and Restore Procedures

### Configuration Backup

**Via Web UI** (recommended):
1. Navigate to Settings
2. Scroll to Configuration Backup/Restore section
3. Click "Export Settings"
4. Save the JSON file to a secure location

**Via API**:
```bash
curl -X GET http://localhost:5000/api/settings/export \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o scidk-config-backup.json
```

### Database Backup

**Automated backup** (recommended):

SciDK includes a backup scheduler. Configure in Settings → Backup:
- Enable automatic backups
- Set schedule (daily, weekly, etc.)
- Set retention policy
- Configure backup location

**Manual SQLite backup**:
```bash
# Stop the application first (important!)
sudo systemctl stop scidk

# Create backup
sqlite3 ~/.scidk/db/files.db ".backup ~/.scidk/db/files.db.backup"

# Or use cp (ensure no active connections)
cp ~/.scidk/db/files.db ~/.scidk/db/files.db.$(date +%Y%m%d_%H%M%S)

# Restart application
sudo systemctl start scidk
```

**Online backup** (using WAL mode):
```bash
# WAL mode allows backups while running
sqlite3 ~/.scidk/db/files.db ".backup /backups/files.db.$(date +%Y%m%d)"
```

### Neo4j Backup

**Via Neo4j dump** (recommended):
```bash
# Stop Neo4j
docker compose -f docker-compose.neo4j.yml stop neo4j

# Create dump
docker compose -f docker-compose.neo4j.yml run --rm neo4j \
  neo4j-admin database dump neo4j \
  --to-path=/backups/neo4j-dump-$(date +%Y%m%d).dump

# Restart Neo4j
docker compose -f docker-compose.neo4j.yml start neo4j
```

**Via Docker volume backup**:
```bash
# Backup Neo4j data directory
sudo tar -czf neo4j-data-$(date +%Y%m%d).tar.gz \
  ./data/neo4j/data
```

### Restore Procedures

**Restore SQLite database**:
```bash
# Stop application
sudo systemctl stop scidk

# Restore from backup
cp ~/.scidk/db/files.db.backup ~/.scidk/db/files.db

# Restart application
sudo systemctl start scidk

# Verify health
curl http://localhost:5000/api/health
```

**Restore configuration**:
1. Navigate to Settings → Configuration Backup/Restore
2. Click "Import Settings"
3. Select your backup JSON file
4. Click "Import"
5. Restart application if prompted

**Restore Neo4j**:
```bash
# Stop Neo4j
docker compose -f docker-compose.neo4j.yml stop neo4j

# Restore dump
docker compose -f docker-compose.neo4j.yml run --rm neo4j \
  neo4j-admin database load neo4j \
  --from-path=/backups/neo4j-dump-20240101.dump

# Start Neo4j
docker compose -f docker-compose.neo4j.yml start neo4j
```

## User Management

### Creating Users

**Via Web UI**:
1. Log in as admin
2. Navigate to Settings → Users (if available)
3. Click "Add User"
4. Enter username, password, and role
5. Click "Create"

**Via SQLite** (if UI not available):
```python
import bcrypt
import sqlite3

# Connect to database
conn = sqlite3.connect('/path/to/files.db')
cursor = conn.cursor()

# Hash password
password = b'secure_password'
hashed = bcrypt.hashpw(password, bcrypt.gensalt())

# Insert user
cursor.execute(
    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
    ('newuser', hashed, 'user')
)
conn.commit()
conn.close()
```

### Managing User Roles

SciDK supports two primary roles:
- **admin**: Full system access, can manage users and settings
- **user**: Standard access to features, cannot manage users

## Monthly Reconciliation Workflow

This example workflow ensures data integrity and identifies discrepancies between indexed files and the graph database.

### Week 1: Health Check and Cleanup

1. **Check system health**:
   ```bash
   curl http://localhost:5000/api/health | jq '.'
   curl http://localhost:5000/api/health/graph | jq '.'
   ```

2. **Review logs for errors**:
   ```bash
   sudo journalctl -u scidk --since "30 days ago" -p err | less
   ```

3. **Check disk space** (should be <80% full):
   ```bash
   df -h ~/.scidk/db/
   df -h ./data/neo4j/
   ```

4. **Clean up old logs** (if needed):
   ```bash
   sudo journalctl --vacuum-time=30d
   ```

### Week 2: Backup Verification

1. **Verify automated backups are running**:
   - Check backup schedule in Settings → Backup
   - Review backup logs for failures
   - Verify backup files exist and are recent

2. **Test a backup restore** (in test environment):
   ```bash
   # Copy production backup to test
   # Restore and verify functionality
   ```

3. **Document backup verification** in operations log

### Week 3: Data Integrity Check

1. **Run scan reconciliation**:
   - Navigate to Files/Datasets
   - Review scan history
   - Identify scans with errors or incomplete status

2. **Check for orphaned data**:
   ```bash
   # Query for files not linked to scans
   curl http://localhost:5000/api/graph/query \
     -X POST \
     -H "Content-Type: application/json" \
     -d '{"query": "MATCH (f:File) WHERE NOT (f)-[:SCANNED_IN]->() RETURN count(f)"}'
   ```

3. **Clean up orphaned relationships**:
   - Use data cleaning features in UI (Files page)
   - Or run Cypher queries to remove orphans

### Week 4: Performance Review

1. **Review scan performance metrics**:
   - Average scan time for common directories
   - Identify slow scans
   - Review progress indicators

2. **Check database performance**:
   ```bash
   # SQLite integrity check
   sqlite3 ~/.scidk/db/files.db "PRAGMA integrity_check;"

   # Optimize if needed
   sqlite3 ~/.scidk/db/files.db "VACUUM;"
   ```

3. **Update documentation**:
   - Document any issues encountered
   - Update runbooks if procedures changed
   - Record performance baselines

### Monthly Report Template

```markdown
# SciDK Monthly Operations Report - [Month Year]

## System Health
- Uptime: [X days/hours]
- Health check status: [Pass/Fail]
- Critical errors: [Count]

## Backups
- Automated backups: [Success count / Total]
- Manual backups: [Count]
- Restore test: [Date] - [Pass/Fail]

## Data Integrity
- Total scans: [Count]
- Failed scans: [Count]
- Orphaned files cleaned: [Count]

## Performance
- Average scan time: [X seconds/minutes]
- Database size: [X GB]
- Largest scan: [X files, Y GB]

## Issues and Resolutions
- [Issue 1]: [Resolution]
- [Issue 2]: [Resolution]

## Action Items
- [ ] Action item 1
- [ ] Action item 2
```

## Alert Management

SciDK includes an alert system for critical events. Configure in Settings → Alerts.

### Alert Types

1. **Import Failed**: Triggered when file import fails
2. **High Discrepancies**: Triggered when scan reconciliation finds mismatches
3. **Backup Failed**: Triggered when automated backup fails
4. **Neo4j Connection Lost**: Triggered when Neo4j becomes unavailable
5. **Disk Space Critical**: Triggered when disk usage exceeds threshold (default 95%)

### Configuring Alerts

1. Navigate to Settings → Alerts
2. Configure SMTP settings for email notifications
3. Enable/disable specific alerts
4. Set recipients for each alert type
5. Adjust thresholds (e.g., disk space warning level)
6. Test alerts using "Test Alert" button

### Responding to Alerts

**Import Failed**:
- Check logs for error details
- Verify file permissions and disk space
- Re-run import after resolving issue

**High Discrepancies**:
- Review scan and graph data
- Run data integrity check
- Use reconciliation tools to fix mismatches

**Backup Failed**:
- Check backup destination is accessible
- Verify disk space is available
- Check backup service logs
- Run manual backup

**Neo4j Connection Lost**:
- Check Neo4j is running: `docker compose -f docker-compose.neo4j.yml ps`
- Review Neo4j logs
- Verify network connectivity
- Restart Neo4j if needed

**Disk Space Critical**:
- Identify large files: `du -sh ~/.scidk/db/* | sort -h`
- Clean up old scans or backups
- Expand storage if persistently full

## Maintenance Tasks

### Weekly Tasks

- [ ] Review application logs for errors
- [ ] Check disk space
- [ ] Verify backups completed successfully
- [ ] Check system health endpoints

### Monthly Tasks

- [ ] Run database integrity check
- [ ] Test backup restore procedure
- [ ] Review and clean up old scans
- [ ] Update documentation
- [ ] Review security audit logs
- [ ] Check for application updates

### Quarterly Tasks

- [ ] Review and update user access
- [ ] Performance tuning and optimization
- [ ] Review and update disaster recovery plan
- [ ] Security audit and vulnerability assessment
- [ ] Capacity planning review

## When to Contact Support

Contact your system administrator or SciDK support when:

1. **Critical system failure**: Application won't start or repeatedly crashes
2. **Data loss**: Cannot restore from backups or data corruption detected
3. **Security incident**: Unauthorized access or suspicious activity
4. **Performance degradation**: Persistent slow performance not resolved by standard procedures
5. **Upgrade issues**: Problems during version upgrade
6. **Neo4j issues**: Cannot connect or restore graph database

### Information to Gather Before Contacting Support

- Application version: Check README.md or git tag
- Error messages: From logs (journalctl output)
- Health check output: From `/api/health` endpoint
- Recent changes: Configuration, upgrades, or operational changes
- Reproduction steps: How to reproduce the issue
- Impact: Number of users affected, criticality

## Performance Optimization

### Database Optimization

**SQLite maintenance**:
```bash
# Run VACUUM to reclaim space and optimize
sqlite3 ~/.scidk/db/files.db "VACUUM;"

# Analyze for query optimization
sqlite3 ~/.scidk/db/files.db "ANALYZE;"
```

**Neo4j maintenance**:
1. Navigate to Neo4j Browser (http://localhost:7474)
2. Run: `CALL db.stats.retrieve('NODE COUNTS');`
3. Run: `CALL db.stats.retrieve('RELATIONSHIP COUNTS');`
4. Consider creating indexes for frequently queried properties

### Scan Performance

- Use **ncdu** or **gdu** for faster filesystem enumeration
- Enable **fast_list** mode for rclone scans (if supported by remote)
- Use **non-recursive** scans for large directory trees
- Adjust **batch size** in Settings → Interpreters

### Application Performance

- Increase allocated memory if frequently encountering OOM errors
- Use **pagination** when browsing large datasets
- Enable **WAL mode** for SQLite (should be default)
- Monitor and limit concurrent scans

## Disaster Recovery

### Recovery Time Objectives (RTO)

- **Configuration**: < 1 hour (restore from settings backup)
- **Database**: < 2 hours (restore SQLite from backup)
- **Graph Database**: < 4 hours (restore Neo4j from dump)

### Recovery Point Objectives (RPO)

- **Configuration**: < 24 hours (daily exports)
- **Database**: < 24 hours (daily backups)
- **Graph Database**: < 24 hours (daily Neo4j backups)

### Disaster Recovery Procedures

See disaster recovery runbook in `dev/ops/` directory for detailed procedures.

## Troubleshooting Quick Reference

For detailed troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

**Quick fixes**:

- **Can't connect to app**: Check if running (`systemctl status scidk`), check port (`netstat -tlnp | grep 5000`)
- **Can't connect to Neo4j**: Check if running (`docker compose ps`), verify credentials in Settings
- **Slow performance**: Check disk space, run VACUUM, restart application
- **Database locked**: Check for multiple processes, verify WAL mode enabled

## Additional Resources

- [DEPLOYMENT.md](DEPLOYMENT.md) - Installation and deployment
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common problems and solutions
- [SECURITY.md](SECURITY.md) - Security best practices
- [API.md](API.md) - API reference and usage
