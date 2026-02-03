# Development Guide

## Feature Flags Documentation

SciDK uses environment variables for feature flags and configuration. The index of all feature flags is automatically generated and maintained in `dev/features/feature-flags.md`.

### Keeping Feature Flags Index Up-to-Date

#### Manual Update

To regenerate the feature flags index:

```bash
make flags-index
```

Or directly:

```bash
python -m dev.tools.feature_flags_index --write
```

#### CI Verification

**Note:** CI verification is currently disabled as the `dev/` directory is a private submodule not accessible to GitHub Actions. The verification step will be re-enabled when the submodule is made public or when feature flags documentation is moved to the main repository.

For local development, you can verify the index is up-to-date:

```bash
make docs-check
```

If you add or modify environment variable usage in the code, regenerate the index before pushing:

```bash
make flags-index
git add dev/features/feature-flags.md
git commit -m "docs: update feature flags index"
```

#### Pre-commit Hook (Optional)

You can set up a git pre-commit hook to automatically regenerate the feature flags index on each commit. This ensures you never forget to update the documentation.

**Setup:**

1. Create or edit `.git/hooks/pre-commit`:

```bash
#!/bin/sh
# Pre-commit hook: regenerate feature flags index if any Python files changed

# Check if any Python files were modified
if git diff --cached --name-only | grep -q '\.py$'; then
    echo "Python files changed, regenerating feature flags index..."
    python -m dev.tools.feature_flags_index --write

    # Check if feature-flags.md was modified
    if ! git diff --exit-code --quiet dev/features/feature-flags.md; then
        echo "Feature flags index updated. Adding to commit..."
        git add dev/features/feature-flags.md
    fi
fi

exit 0
```

2. Make it executable:

```bash
chmod +x .git/hooks/pre-commit
```

**How it works:**
- Runs before every commit
- If Python files were modified, regenerates the feature flags index
- If the index changed, automatically stages it for the commit
- Ensures your commits always include updated documentation

**Note:** This hook is optional. The CI check will catch stale documentation even if you don't use the hook.

### Adding New Feature Flags

When adding new environment variables to the code:

1. Use the standard pattern with `os.environ.get()`
2. Include default values where appropriate
3. Regenerate the index: `make flags-index`
4. Commit both the code and the updated index

Example:

```python
# Good: includes default
enabled = os.environ.get('SCIDK_MY_FEATURE', '0') == '1'

# Also good: documents absence
api_key = os.environ.get('SCIDK_API_KEY')  # None if not set
```

### Viewing the Feature Flags Index

To view the current index without writing:

```bash
python -m dev.tools.feature_flags_index
```

Or view the file directly:

```bash
cat dev/features/feature-flags.md
```

## Testing

### Running Tests

```bash
# Unit tests only
make unit

# Integration tests
make integration

# E2E tests (requires running server)
BASE_URL=http://localhost:5000 make e2e

# All tests
make check
```

### Test Organization

- Unit tests: Fast, no external dependencies
- Integration tests: May use database, filesystem
- E2E tests: Full browser automation with Playwright

See `Makefile` for more test targets including headed mode, parallel execution, and debugging options.
