## Interpreting Files from Rclone Remotes

### When to Use a Mount vs. Direct Streaming

Direct streaming via rclone (using `rclone cat`) lets the application interpret remote files without mounting. This works well for small to medium-sized file sets, but cloud storage APIs impose rate limits that can affect larger operations.

#### Recommended Thresholds

- Suggest mounting when: A single remote scan contains ≥ 300–500 files
- Practical per-request streaming batch sizes:
  - Google Drive: 500–1000 files per request
  - Dropbox: 300–800 files per request
- Default file size cap: 1 MB per file for text/code interpretation (increase selectively for notebooks if needed)

#### Why Mounts Can Be Better for Large Sets

1. Reduces API round-trips: Each interpreted file typically requires at least one remote API call (`rclone cat`)
2. Avoids rate limiting: Cloud providers (Google Drive, Dropbox) throttle frequent small reads with 429/403 responses
3. Improves reliability: Better throughput and fewer timeouts on large batches
4. Predictable resource usage: Enables smoother local-like reads for interpreter CPU/RAM management

#### Provider-Specific Limits

Google Drive:
- Sustainable rate: 4–5 requests/sec sustained, bursts up to ~10 req/sec
- Returns `403 rateLimitExceeded` or `429` with `Retry-After` headers when throttled
- rclone's adaptive pacer handles backoff automatically

Dropbox:
- Sustainable rate: 2–4 requests/sec sustained, bursts ≤ 8–10 req/sec
- More sensitive to parallel reads, keep concurrency low (2–3 simultaneous connections)

### Using Rclone Interpretation Settings

Navigate to Settings → Rclone Interpretation to configure:

- Suggest-mount threshold: Number of files in a scan that triggers mount recommendation
- Max files per interpretation batch: Upper limit for files processed in a single request (floor 100, ceiling 2000)
- Chunked processing: For large scans, the system automatically processes files in chunks using these limits

When viewing a large rclone scan, you'll see a banner suggesting to mount the remote for better performance. The "Re-interpret scan" action runs in manageable chunks based on these settings.
