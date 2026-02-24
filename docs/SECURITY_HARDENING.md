# Script Sandbox Security Analysis & Hardening Recommendations

## Current Security Model

**What's Protected:**
- ✅ Import whitelist blocks: `subprocess`, `requests`, `socket`, `urllib`, `http`, `email`, `smtplib`
- ✅ Subprocess isolation (separate process)
- ✅ 10-second timeout (prevents infinite loops)
- ✅ Minimal environment variables (only PATH)
- ✅ Validation required before activation

**What's NOT Protected:**
- ❌ Full filesystem access (can read/write/delete ANY file)
- ❌ SQLite database access (can corrupt/delete any .db file)
- ❌ No resource limits (CPU, memory, disk I/O)
- ❌ No chroot/jail (can access entire system)
- ❌ Working directory not restricted

## Critical Vulnerabilities

### 1. **File System Access** (HIGH RISK)
```python
# Malicious script could:
import os, shutil

# Delete important files
os.remove('/home/user/.scidk/scidk.db')
shutil.rmtree('/home/user/important_data')

# Read sensitive data
with open('/home/user/.ssh/id_rsa', 'r') as f:
    private_key = f.read()
    # Send to results[] which goes to UI

# Overwrite system files (if running as root)
with open('/etc/passwd', 'w') as f:
    f.write('malicious content')
```

### 2. **Database Access** (HIGH RISK)
```python
import sqlite3

# Corrupt the main database
conn = sqlite3.connect('/home/user/.scidk/scidk.db')
conn.execute('DROP TABLE scripts;')
conn.execute('DROP TABLE script_executions;')
conn.commit()
```

### 3. **Resource Exhaustion** (MEDIUM RISK)
```python
# Fill up disk space
with open('/tmp/huge_file', 'wb') as f:
    f.write(b'X' * (1024**3 * 10))  # 10GB file

# Memory bomb (before 10s timeout)
data = 'X' * (1024**3 * 5)  # 5GB string
```

### 4. **Information Disclosure** (HIGH RISK)
```python
import os

# Exfiltrate environment variables, file contents
results = [
    {'key': k, 'value': v} for k, v in os.environ.items()
]

# Read all .env files
for root, dirs, files in os.walk('/home/user'):
    for file in files:
        if file.endswith('.env'):
            with open(os.path.join(root, file)) as f:
                results.append({'file': file, 'contents': f.read()})
```

## Trust Model: Who Can Create Scripts?

**Current Assumptions:**
- Scripts are created by trusted administrators
- Validation catches syntax/runtime errors, NOT malicious behavior
- Users can see script code before running

**Risk Level by User Type:**
- **Single-user dev environment:** LOW - user can already do all of this
- **Multi-user system:** CRITICAL - any user who can create scripts can attack others
- **Public/demo deployment:** CRITICAL - must not allow arbitrary script creation

## Hardening Options (Ordered by Effectiveness)

### **Tier 1: Essential (Implement for Multi-User)**

#### 1.1. Read-Only Filesystem Mount
```python
# In script_sandbox.py run_sandboxed()
import tempfile
import shutil

# Create temporary read-only working directory
with tempfile.TemporaryDirectory() as tmpdir:
    # Copy only necessary files (read-only)
    # Run subprocess with cwd=tmpdir
    subprocess.run([...], cwd=tmpdir)
```

**Pros:** Prevents filesystem damage
**Cons:** Breaks scripts that need to write files
**Effort:** Medium (2-3 hours)

#### 1.2. Restrict SQLite Access to Temp Databases Only
```python
# Wrap sqlite3 to only allow temp databases
ALLOWED_IMPORTS.remove('sqlite3')

# Provide safe wrapper in execution context:
import sqlite3
import tempfile

class SafeSQLite:
    def connect(self, database=':memory:'):
        if database == ':memory:':
            return sqlite3.connect(':memory:')
        # Only allow temp directory
        if not database.startswith('/tmp/'):
            raise PermissionError("Database must be in /tmp/")
        return sqlite3.connect(database)

# In validation context:
global_namespace['sqlite3'] = SafeSQLite()
```

**Pros:** Prevents database corruption
**Cons:** Scripts can't access real databases
**Effort:** Low (1 hour)

#### 1.3. Resource Limits via ulimit (Linux only)
```python
import resource

def run_sandboxed_with_limits(code, timeout=10):
    # Limit memory to 512MB
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    # Limit CPU time to 10s
    resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
    # Limit file size to 100MB
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))

    # Run subprocess
    subprocess.run([...])
```

**Pros:** Prevents resource exhaustion
**Cons:** Linux-only, requires careful tuning
**Effort:** Low (1 hour)

### **Tier 2: Strong (Container-Based Isolation)**

#### 2.1. Docker Container Execution
```python
def run_sandboxed(code, timeout=10):
    # Write code to temp file
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
        f.write(code)
        code_file = f.name

    # Run in isolated Docker container
    result = subprocess.run([
        'docker', 'run',
        '--rm',                          # Remove after execution
        '--network=none',                # No network access
        '--memory=512m',                 # Memory limit
        '--cpus=1',                      # CPU limit
        '--read-only',                   # Read-only filesystem
        '--tmpfs=/tmp:rw,size=100m',    # Temp storage only
        f'--timeout={timeout}',
        'python:3.11-slim',
        'python', '-c', code
    ], capture_output=True, timeout=timeout)
```

**Pros:** Strong isolation, cross-platform
**Cons:** Requires Docker, slower startup, heavier
**Effort:** Medium (3-4 hours)

#### 2.2. Bubblewrap (Linux Sandbox)
```python
# Lightweight alternative to Docker (Linux only)
subprocess.run([
    'bwrap',
    '--ro-bind', '/usr', '/usr',        # Read-only system
    '--ro-bind', '/lib', '/lib',
    '--ro-bind', '/lib64', '/lib64',
    '--tmpfs', '/tmp',                  # Writable temp only
    '--unshare-all',                    # Isolate namespaces
    '--die-with-parent',
    'python3', '-c', code
])
```

**Pros:** Lightweight, fast, strong isolation
**Cons:** Linux-only, requires bubblewrap install
**Effort:** Medium (2-3 hours)

### **Tier 3: Maximum (Production-Grade)**

#### 3.1. Dedicated Sandbox Service
- Separate microservice for script execution
- Runs in isolated VM or container
- Communicates via API only
- Can be reset/redeployed if compromised

**Effort:** High (1-2 weeks)

#### 3.2. WebAssembly (WASM) Execution
- Compile Python to WASM
- Run in browser-like sandbox
- True isolation, no filesystem access

**Effort:** Very High (research required)

## Recommendations by Deployment Type

### **Single-User Development (Current)**
**Risk Level:** LOW
**Recommendation:** Current model is acceptable
- User can already access their own files
- Validation catches accidental errors
- Add basic resource limits (Tier 1.3) for safety

### **Multi-User Server**
**Risk Level:** CRITICAL
**Recommendation:** Implement Tier 1 + Tier 2
1. Read-only filesystem or temp directory only
2. Restrict SQLite to temp databases
3. Resource limits (memory, CPU, disk)
4. Consider Docker containers for strong isolation

### **Public Demo / Untrusted Users**
**Risk Level:** CRITICAL
**Recommendation:** Tier 2 (Docker) or disable script creation
- Do NOT allow arbitrary script creation
- Pre-load only validated builtin scripts
- Mark them as non-editable
- OR: Use Docker with full isolation

## Immediate Action Items

### For Current MVP (Before Demo):

**Option A: Trust Model (Recommended for MVP)**
1. ✅ Keep current sandbox
2. ✅ Add resource limits (Tier 1.3) - 1 hour
3. ✅ Document: "Scripts can only be created by administrators"
4. ✅ Add UI warning: "Scripts have filesystem access. Only create/activate scripts from trusted sources."
5. ✅ Add authentication check: Only admins can create/edit/activate scripts

**Option B: Hardening (Better for multi-user)**
1. Implement read-only filesystem (Tier 1.1) - 2-3 hours
2. Restrict SQLite access (Tier 1.2) - 1 hour
3. Add resource limits (Tier 1.3) - 1 hour
4. Test all builtin scripts still work
**Total:** 4-5 hours

### Post-MVP (Production Hardening):
1. Implement Docker-based execution (Tier 2.1)
2. Add audit logging for all script executions
3. Add permission system for script activation
4. Consider dedicated sandbox service for high-security deployments

## Security Best Practices

**For Script Authors:**
1. Never put credentials in script code
2. Use parameterized queries for databases
3. Validate all inputs
4. Handle errors gracefully
5. Don't trust user-provided file paths

**For System Administrators:**
1. Only activate scripts you've reviewed
2. Run SciDK with minimal privileges (not root)
3. Keep backups of databases
4. Monitor script execution logs
5. Use file permissions to protect sensitive data

## Detection & Monitoring

**Add to future roadmap:**
1. Audit log all script executions with user, timestamp, parameters
2. Monitor filesystem access during script execution
3. Alert on suspicious patterns (reading .ssh, .env files, etc.)
4. Rate limiting on script execution
5. Rollback mechanism for database changes

## Conclusion

**Current Status:** ⚠️ Suitable for single-user development, NOT for multi-user production

**MVP Recommendation:** Add UI warning + admin-only script creation (30 min)

**Production Recommendation:** Implement Tier 1 hardening at minimum (4-5 hours)

**For public/untrusted environments:** Require Docker-based isolation (Tier 2)
