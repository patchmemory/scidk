"""The one place a ``(provider_id, root_id)`` pair becomes a host label.

File and Folder nodes are keyed by ``(path, host)``, and ``host`` is this label:
``local:<hostname>``, ``mounted:<root>``, ``rclone:<remote>``. Commit writes it,
so everything that later matches a committed file (Collect, the sweep,
``files.remote``) has to derive it the same way. It used to be copied into five
places, and the Files page sent the bare provider id (``local_fs``) instead,
which matched nothing and created stub nodes beside the real ones.
"""
from __future__ import annotations

import socket
from typing import Optional

#: Provider ids the Files page knows. A ``host`` value equal to one of these is
#: a provider id sent by mistake, not a host label.
PROVIDER_IDS = ('local_fs', 'mounted_fs', 'rclone')


def host_id_for(provider_id: Optional[str], root_id: Optional[str] = None) -> str:
    provider_id = (provider_id or '').strip()
    root_id = (root_id or '').strip()
    if provider_id == 'local_fs':
        return f"local:{socket.gethostname()}"
    if provider_id == 'mounted_fs':
        return f"mounted:{root_id}"
    if provider_id == 'rclone':
        return f"rclone:{root_id.rstrip(':')}"
    return f"{provider_id}:{root_id}" if root_id else provider_id


def is_host_label(value: Optional[str]) -> bool:
    """True for a real host label, False for empty or a bare provider id."""
    value = (value or '').strip()
    return bool(value) and value not in PROVIDER_IDS
