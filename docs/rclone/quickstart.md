See also dev/ops/rclone/rclone-quickstart.md if available in your checkout.

Include the following in README:

- Enable provider: export SCIDK_PROVIDERS=local_fs,mounted_fs,rclone
- UI usage: Scan Files panel → Provider: Rclone Remotes; Load Roots; Browse gdrive:folder; Scan.
- API:
  - GET /api/provider_roots?provider_id=rclone
  - GET /api/browse?provider_id=rclone&path=<remote:path>&recursive=true|false&max_depth=1..N&fast_list=true|false
  - POST /api/scan { provider_id: 'rclone', path: '<remote:path>' }

Install rclone:
- Linux: curl https://rclone.org/install.sh | sudo bash
- macOS: brew install rclone
- Windows: choco install rclone

Configure:
- rclone config → new remote (drive/dropbox/s3)
- Verify: rclone listremotes; rclone ls gdrive:; rclone lsjson gdrive:

Optional FUSE mount:
- rclone mount gdrive: data/mounts/gdrive --read-only --vfs-cache-mode=off --dir-cache-time=1m --daemon
- Unmount: fusermount -u data/mounts/gdrive
