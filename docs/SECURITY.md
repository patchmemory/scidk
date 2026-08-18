# SciDK Security Guide

This guide covers the security architecture, best practices, compliance considerations, and incident response procedures for SciDK deployments.

## Security Architecture Overview

SciDK implements defense-in-depth security with multiple layers of protection:

1. **Authentication & Authorization**: Multi-user authentication with role-based access control (RBAC)
2. **Data Encryption**: Encryption at rest and in transit
3. **Audit Logging**: Comprehensive audit trails for all system activities
4. **Session Management**: Secure session handling with timeout controls
5. **Input Validation**: Protection against injection attacks
6. **Secure Configuration**: Encrypted credential storage

## Authentication and Authorization

### User Authentication

SciDK supports session-based authentication with the following features:

**Password Security**:
- Passwords hashed using bcrypt with salt
- Minimum password complexity requirements (configurable)
- Protection against brute force attacks
- Secure password reset mechanisms

**Session Management**:
- Session-based authentication using secure cookies
- Configurable session timeout (default: 30 minutes)
- Auto-lock after inactivity
- Session invalidation on logout
- CSRF protection enabled

**Example: Enabling Authentication**:
```python
# In settings database or via UI
auth_config = {
    "enabled": True,
    "session_timeout": 1800,  # 30 minutes
    "password_min_length": 8,
    "require_complex_password": True
}
```

### Role-Based Access Control (RBAC)

SciDK implements RBAC with the following roles:

**Admin Role**:
- Full system access
- User management capabilities
- Settings configuration
- Backup and restore operations
- Security configuration

**User Role**:
- Standard feature access
- File browsing and searching
- Graph visualization
- Chat interface
- Data exploration

**Permissions Enforcement**:
```python
# Example permission check (internal)
@require_role('admin')
def delete_user(user_id):
    # Only admins can delete users
    pass
```

### Creating Secure User Accounts

**Best Practices**:
1. Use strong, unique passwords (minimum 12 characters)
2. Enable multi-factor authentication (if available)
3. Limit admin accounts to necessary personnel
4. Regular password rotation (every 90 days)
5. Disable or remove unused accounts

**Example: Creating Admin User**:
```bash
# Via Python script
python3 -c "
from scidk.core.auth import create_user
create_user('admin', 'SecurePassword123!', role='admin')
"
```

## Data Encryption

### Encryption at Rest

**SQLite Database**:
- File-level encryption using OS filesystem encryption
- Sensitive data (passwords, API keys) encrypted using Fernet (symmetric encryption)
- Encryption keys stored securely (not in version control)

**Neo4j Database**:
- Enterprise Edition supports transparent data encryption
- Community Edition: Use filesystem-level encryption

**Example: Filesystem Encryption (Linux)**:
```bash
# LUKS encryption for data partition
sudo cryptsetup luksFormat /dev/sdb1
sudo cryptsetup luksOpen /dev/sdb1 encrypted_data
sudo mkfs.ext4 /dev/mapper/encrypted_data
sudo mount /dev/mapper/encrypted_data /var/lib/scidk
```

**Backup Encryption**:
```bash
# Encrypt backups with GPG
gpg --symmetric --cipher-algo AES256 backup.db
```

### Encryption in Transit

**HTTPS/TLS**:
All production deployments should use HTTPS:

```nginx
# nginx configuration
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/scidk.crt;
    ssl_certificate_key /etc/ssl/private/scidk.key;

    # Strong SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers on;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
```

**Neo4j TLS**:
Configure Neo4j to use encrypted Bolt connections:

```bash
# neo4j.conf
dbms.connector.bolt.tls_level=REQUIRED
dbms.ssl.policy.bolt.enabled=true
dbms.ssl.policy.bolt.base_directory=certificates/bolt
```

**API Communication**:
- All API endpoints should be accessed via HTTPS
- Credentials never transmitted in plain text
- Bearer tokens or session cookies for authentication

## Audit Logging

### Audit Trail Features

SciDK maintains comprehensive audit logs for:

1. **User Authentication Events**:
   - Login attempts (success/failure)
   - Logout events
   - Session expiration
   - Password changes

2. **Data Access Events**:
   - File access and downloads
   - Dataset queries
   - Graph queries
   - Export operations

3. **Administrative Actions**:
   - User creation/modification/deletion
   - Settings changes
   - Backup operations
   - System configuration changes

4. **Security Events**:
   - Failed authentication attempts
   - Permission denied errors
   - Suspicious activity patterns

### Audit Log Format

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "event_type": "user.login",
  "user": "admin",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0...",
  "status": "success",
  "details": {
    "session_id": "sess_abc123"
  }
}
```

### Accessing Audit Logs

**Via systemd journals**:
```bash
sudo journalctl -u scidk | grep AUDIT
```

**Via SQLite database**:
```sql
SELECT * FROM audit_log
WHERE timestamp > datetime('now', '-7 days')
ORDER BY timestamp DESC;
```

### Audit Log Retention

**Recommended Retention Policies**:
- Security events: 1 year minimum
- Authentication logs: 90 days minimum
- Administrative actions: 1 year minimum
- Data access: 30-90 days (or per compliance requirements)

**Configure retention**:
```bash
# systemd journal retention
sudo journalctl --vacuum-time=365d
```

## Security Best Practices

### Deployment Security

**1. Network Security**:
- Deploy behind firewall
- Use private networks for database connections
- Limit exposed ports (only 443/80 for web, 7687 for internal Neo4j)
- Implement IP allowlisting for admin access

**Example firewall rules (ufw)**:
```bash
# Allow HTTPS
sudo ufw allow 443/tcp

# Allow Neo4j only from app server
sudo ufw allow from 10.0.1.10 to any port 7687

# Deny all other incoming
sudo ufw default deny incoming
sudo ufw enable
```

**2. Operating System Security**:
- Keep OS and packages updated
- Use dedicated service account (non-root)
- Disable unnecessary services
- Configure SELinux/AppArmor policies

**3. Database Security**:
- Change default passwords immediately
- Use strong authentication credentials
- Regular security patches and updates
- Database access restricted to application only

**4. Application Security**:
- Run as non-privileged user
- Use virtual environment isolation
- Keep dependencies updated
- Regular security scanning

### Credential Management

**Best Practices**:
1. Never commit credentials to version control
2. Use environment variables or secret management systems
3. Rotate credentials regularly (every 90 days)
4. Use different credentials for dev/test/prod
5. Encrypt credentials at rest

**Example: Secret Management**:
```bash
# Use environment variables
export NEO4J_PASSWORD=$(vault read -field=password secret/neo4j)

# Or use .env file (not in git)
echo "NEO4J_AUTH=neo4j/$(openssl rand -base64 32)" >> .env
chmod 600 .env
```

**Credential Storage**:
- SciDK stores encrypted credentials in SQLite
- Encryption key should be stored separately
- Consider using external secret managers (HashiCorp Vault, AWS Secrets Manager)

### Input Validation

SciDK implements input validation to prevent:

**SQL Injection**:
- Parameterized queries for all database access
- ORM-based database interactions
- Input sanitization

**Command Injection**:
- No shell command construction from user input
- Subprocess calls use argument arrays (not shell=True)
- Path validation for filesystem operations

**Cross-Site Scripting (XSS)**:
- HTML escaping in templates
- Content Security Policy headers
- Input sanitization

**Path Traversal**:
- Path normalization
- Validation against allowed directories
- No direct user input in file paths

### Session Security

**Configuration**:
```python
# Flask session configuration
app.config.update(
    SESSION_COOKIE_SECURE=True,      # HTTPS only
    SESSION_COOKIE_HTTPONLY=True,    # No JavaScript access
    SESSION_COOKIE_SAMESITE='Lax',   # CSRF protection
    PERMANENT_SESSION_LIFETIME=1800  # 30 minutes
)
```

**Session Management**:
- Automatic session expiration
- Session invalidation on logout
- Session regeneration after privilege escalation
- Single sign-on support (if configured)

### Secure Headers

**Recommended HTTP Security Headers**:
```nginx
# nginx configuration
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

## Compliance Considerations

### HIPAA Compliance

For healthcare data:

**Required Controls**:
1. **Access Control**: RBAC with unique user accounts
2. **Audit Controls**: Comprehensive audit logging
3. **Integrity Controls**: Data validation and checksums
4. **Transmission Security**: TLS/HTTPS for all communications
5. **Authentication**: Strong password policies
6. **Encryption**: Data encryption at rest and in transit

**BAA Requirements**:
- Ensure Business Associate Agreement with cloud providers
- Document security policies and procedures
- Regular security risk assessments
- Incident response procedures

**PHI Handling**:
- Minimize PHI exposure
- De-identify data when possible
- Secure disposal procedures
- Access logging for all PHI

### GDPR Compliance

For European data:

**Right to Access**:
- Provide user data export functionality
- API endpoints for data retrieval

**Right to Erasure**:
- User deletion removes all associated data
- Cascade delete for related records
- Audit log of deletions (without retaining PII)

**Right to Portability**:
- Export in machine-readable format (JSON, CSV)
- Configuration backup/export functionality

**Data Protection**:
- Encryption at rest and in transit
- Access controls and audit logs
- Privacy by design and default
- Data minimization

**Breach Notification**:
- 72-hour breach notification requirement
- Incident response procedures
- Contact data protection authorities

### SOC 2 Compliance

For service organizations:

**Trust Services Criteria**:
1. **Security**: Access controls, encryption, monitoring
2. **Availability**: Uptime, redundancy, disaster recovery
3. **Processing Integrity**: Data validation, error handling
4. **Confidentiality**: Encryption, access controls
5. **Privacy**: Data handling, consent management

**Implementation**:
- Document security policies
- Regular security assessments
- Vendor management
- Change management procedures
- Incident response plan

## Vulnerability Management

### Security Updates

**Update Process**:
1. Monitor security advisories for dependencies
2. Test updates in staging environment
3. Schedule maintenance window
4. Apply updates and verify
5. Document changes

**Automated Scanning**:
```bash
# Scan Python dependencies
pip install safety
safety check

# Scan for vulnerabilities
npm audit  # If using Node.js tools
```

### Penetration Testing

**Recommended Schedule**:
- Annual penetration testing
- After major releases
- Before compliance audits

**Testing Scope**:
- Web application security
- API security
- Authentication mechanisms
- Database security
- Network security

### Responsible Disclosure

**Security Issue Reporting**:
- Email: security@your-org.com
- PGP key available for encrypted reports
- Expected response time: 48 hours
- Coordinated disclosure policy

## Incident Response

### Incident Response Plan

**Phase 1: Detection**
- Monitor audit logs for suspicious activity
- Alert system for security events
- User reports of suspicious behavior

**Phase 2: Containment**
- Isolate affected systems
- Disable compromised accounts
- Block malicious IP addresses
- Preserve evidence

**Phase 3: Eradication**
- Identify root cause
- Remove malicious code/access
- Patch vulnerabilities
- Reset compromised credentials

**Phase 4: Recovery**
- Restore from clean backups
- Verify system integrity
- Monitor for recurrence
- Gradual service restoration

**Phase 5: Lessons Learned**
- Document incident timeline
- Identify improvements
- Update procedures
- Train personnel

### Incident Response Procedures

**Security Breach Response**:
```bash
# 1. Isolate the system
sudo systemctl stop scidk
sudo ufw deny from suspicious_ip

# 2. Preserve evidence
sudo journalctl -u scidk > incident_logs.txt
cp ~/.scidk/db/files.db incident_db_$(date +%Y%m%d).backup

# 3. Reset credentials
./scripts/reset_all_passwords.sh

# 4. Restore from known good backup
cp ~/.scidk/db/files.db.verified ~/.scidk/db/files.db

# 5. Restart with monitoring
sudo systemctl start scidk
tail -f /var/log/syslog | grep scidk
```

**Data Breach Response**:
1. Determine scope: What data was accessed?
2. Notify affected parties (per regulations)
3. Document the breach
4. Report to authorities (if required)
5. Implement additional controls

### Incident Communication

**Internal Communication**:
- Notify security team immediately
- Escalate to management within 1 hour
- Brief technical team on containment

**External Communication**:
- Notify affected users (if PII compromised)
- Regulatory notification (if required)
- Public disclosure (if significant breach)

**Communication Template**:
```
Subject: Security Incident Notification

We are writing to inform you of a security incident that occurred on [date].

Incident Type: [Unauthorized access / Data breach / etc.]
Data Affected: [Description]
Actions Taken: [Containment, investigation, etc.]
User Actions Required: [Password reset, etc.]

We take security seriously and have implemented additional measures...
```

## Security Monitoring

### Real-Time Monitoring

**Monitor for**:
- Failed login attempts (>5 in 5 minutes)
- Unusual access patterns
- Large data exports
- Configuration changes
- Database connection errors

**Alert Configuration**:
```python
# Example alert rule
alert_rules = {
    "failed_logins": {
        "condition": "count > 5 in 5 minutes",
        "action": "email_admin",
        "severity": "high"
    }
}
```

### Security Metrics

**Track**:
- Authentication success/failure rate
- Average session duration
- API error rates
- Disk space usage
- Database connection pool status

### Log Analysis

**Regular Reviews**:
- Daily: Security event review
- Weekly: Authentication pattern analysis
- Monthly: Comprehensive security audit
- Quarterly: Access control review

```bash
# Example log analysis
# Failed logins
sudo journalctl -u scidk | grep "LOGIN_FAILED" | wc -l

# Unique IP addresses
sudo journalctl -u scidk | grep "LOGIN" | awk '{print $X}' | sort -u | wc -l
```

## Security Checklist

### Deployment Security Checklist

- [ ] Change all default passwords
- [ ] Enable HTTPS with valid certificates
- [ ] Configure firewall rules
- [ ] Enable authentication and RBAC
- [ ] Set strong session timeout
- [ ] Enable audit logging
- [ ] Encrypt sensitive data at rest
- [ ] Configure secure backup procedures
- [ ] Set up security monitoring and alerts
- [ ] Document incident response procedures
- [ ] Perform security assessment
- [ ] Train administrators on security procedures

### Monthly Security Review

- [ ] Review audit logs for anomalies
- [ ] Check for security updates
- [ ] Verify backup integrity
- [ ] Review user accounts and permissions
- [ ] Test disaster recovery procedures
- [ ] Review alert configurations
- [ ] Update documentation

## Additional Resources

- **Deployment Guide**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Operations Manual**: [OPERATIONS.md](OPERATIONS.md)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **NIST Cybersecurity Framework**: https://www.nist.gov/cyberframework
- **CIS Controls**: https://www.cisecurity.org/controls/
