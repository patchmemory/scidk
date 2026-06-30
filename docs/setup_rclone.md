# Rclone Setup

Ops reference for configuring rclone remotes used by a SciDK instance. For UI/API usage of the rclone provider see [`docs/rclone/quickstart.md`](rclone/quickstart.md); for FUSE mounts see [`docs/rclone/mount-examples.md`](rclone/mount-examples.md).

## Install rclone

Install from the official package (do not vendor the binary). See <https://rclone.org/install/>.

```bash
# Linux
curl https://rclone.org/install.sh | sudo bash
# macOS
brew install rclone

rclone version
```

SciDK shells out to whatever `rclone` is on `PATH` (`shutil.which('rclone')`). It must be installed on the same host as the SciDK process — not just inside a container the app cannot reach.

## How SciDK uses rclone

`RcloneProvider` (`scidk/core/providers.py`) drives the `rclone` CLI directly:

- **Discover remotes:** `rclone listremotes` → populates the provider roots (each line like `dropbox:`).
- **Browse / scan:** `rclone lsjson <remote:path>` → JSON entries (`Name`, `Path`, `Size`, `IsDir`) consumed by the scan loop.
- **Fetch content:** `rclone cat <remote:path>` via `provider.cat()` / `provider.open()`.

Any remote you create with `rclone config` is therefore visible to SciDK automatically — there is no separate SciDK-side remote registry. Enable the provider with:

```bash
export SCIDK_PROVIDERS=local_fs,mounted_fs,rclone
```

Verify a remote is reachable before scanning:

```bash
rclone listremotes              # SciDK sees exactly these
rclone lsjson <remote>:         # what a scan will enumerate
```

## Configuring remotes

Run `rclone config` and follow the interactive prompts. Below are the three remote types used in this deployment. OAuth backends (SharePoint, Dropbox) need a browser for the initial token grant — if configuring on a headless server, run `rclone authorize` on a machine with a browser and paste the token, or use `rclone config` over an SSH tunnel.

### SharePoint (Microsoft OneDrive provider)

SharePoint document libraries are accessed through rclone's `onedrive` backend.

```bash
rclone config
# n) New remote
# name> sharepoint
# Storage> onedrive
# Leave client_id / client_secret blank to use rclone's defaults
# region> 1 (Microsoft Cloud Global)
# Use auto config? > y  (opens browser for OAuth)
# Then choose the site type:
#   - "SharePoint site" / "Search for a SharePoint site"
#   - enter the site name or URL, pick the document library (drive)
```

Confirm:

```bash
rclone lsd sharepoint:
```

### Dropbox

```bash
rclone config
# n) New remote
# name> dropbox
# Storage> dropbox
# Leave client_id / client_secret blank
# Use auto config? > y  (opens browser for OAuth)
```

Confirm:

```bash
rclone lsd dropbox:
```

### SFTP or mounted path (e.g. `/mnt/server`)

For a local mount (NFS/CIFS already mounted by the OS, like the BMC-Lab6 archive at `/mnt/server`), you do **not** need an rclone remote at all — use SciDK's `mounted_fs` provider and point a scan at the path directly.

To reach a server over SSH instead, configure an SFTP remote:

```bash
rclone config
# n) New remote
# name> server
# Storage> sftp
# host> server.example.mit.edu
# user> <username>
# port> 22
# Auth: key_file> /home/scidk/.ssh/id_ed25519   (preferred)
#       or set a password
```

Confirm:

```bash
rclone lsd server:/path/to/data
```

## Reconnecting an expired OAuth token

OAuth backends (SharePoint, Dropbox) hold refresh tokens that can expire or be revoked. Scans then fail with auth errors. Re-grant access without recreating the remote:

```bash
rclone config reconnect sharepoint:
rclone config reconnect dropbox:
```

This reopens the browser OAuth flow and rewrites the token in place. Verify afterward with `rclone lsd <remote>:`.

## Troubleshooting

Diagnose any failure by reproducing the exact call SciDK makes, with verbose logging:

```bash
rclone lsjson <remote>:<path> -vv
```

| Symptom | Likely cause | Fix |
|---|---|---|
| `rclone not installed or not on PATH` from SciDK | `rclone` not visible to the app's user/environment | Install rclone for the SciDK service user; confirm `which rclone` |
| Remote missing from SciDK provider roots | Not in `rclone listremotes`, or `rclone` is a different config/user | Check `rclone config file` location; run `rclone listremotes` as the SciDK user |
| `401`/`403` / `token expired` / `invalid_grant` | OAuth token expired or revoked | `rclone config reconnect <remote>:` |
| `directory not found` / empty `lsjson` | Wrong path, or backend has no folder placeholders | Verify with `rclone lsd <remote>:`; check casing and the document-library name |
| Hang or timeout on large dirs | Backend slow to enumerate recursively | Scan with a bounded depth, or try `--fast-list` (provider retries without it on failure) |
| `couldn't connect SSH` | SFTP host/key/firewall | Test `ssh user@host`; confirm `key_file` path and permissions (`600`) |

Useful checks:

```bash
rclone config file          # which config is in effect
rclone config show <remote> # inspect a remote's settings (redacts secrets)
rclone about <remote>:      # quota / connectivity sanity check
```
