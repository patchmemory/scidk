See also dev/ops/rclone/mount-examples.md if available.

Examples:
- rclone mount gdrive: data/mounts/gdrive --read-only --vfs-cache-mode=off --dir-cache-time=1m --daemon
- rclone mount dropbox: data/mounts/dropbox --read-only --vfs-cache-mode=off --dir-cache-time=1m --daemon
- Unmount (Linux): fusermount -u data/mounts/gdrive
