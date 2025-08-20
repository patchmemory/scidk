from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple
import os

# Optional dependency for mounted disks
try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


@dataclass
class ProviderDescriptor:
    id: str
    display_name: str
    capabilities: List[str]
    auth: Dict[str, str]


@dataclass
class Entry:
    id: str
    name: str
    type: str  # file|folder
    size: int
    mtime: float


@dataclass
class DriveInfo:
    id: str
    name: str
    path: str


class FilesystemProvider:
    """Abstract provider interface for browsing and scanning filesystems."""
    id: str = ""
    display_name: str = ""

    def initialize(self, app, config: Dict):  # noqa: D401
        self.app = app
        self.config = config or {}

    def status(self, app) -> Dict:
        return {"ok": True, "message": "ok"}

    def list_roots(self) -> List[DriveInfo]:
        raise NotImplementedError

    def list(self, root_id: str, path: str, page_token: Optional[str] = None, page_size: Optional[int] = None) -> Dict:
        raise NotImplementedError

    def get_entry(self, entry_id: str) -> Entry:
        raise NotImplementedError

    def open(self, entry_id: str):  # Optional
        raise NotImplementedError

    def resolve_scan_target(self, input: Dict) -> Dict:
        """Return { provider_id, root_id, path, label }"""
        raise NotImplementedError

    def enumerate_files(self, scan_target: Dict, recursive: bool, progress_cb: Optional[Callable[[int], None]] = None) -> Iterator[Path]:
        raise NotImplementedError

    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id=self.id,
            display_name=self.display_name,
            capabilities=["browse", "read", "list_roots"],
            auth={"type": "none"},
        )


class LocalFSProvider(FilesystemProvider):
    id = "local_fs"
    display_name = "Local Files"

    def list_roots(self) -> List[DriveInfo]:
        # Single pseudo-root representing the filesystem root
        root = Path("/")
        return [DriveInfo(id=str(root), name=str(root), path=str(root))]

    def _norm(self, p: str) -> Path:
        return Path(p).expanduser().resolve()

    def list(self, root_id: str, path: str, page_token: Optional[str] = None, page_size: Optional[int] = None) -> Dict:
        base = self._norm(path or root_id or "/")
        if not base.exists():
            return {"entries": []}
        items: List[Entry] = []
        for child in base.iterdir():
            try:
                st = child.stat()
                items.append(Entry(
                    id=str(child.resolve()),
                    name=child.name or str(child),
                    type="folder" if child.is_dir() else "file",
                    size=0 if child.is_dir() else int(st.st_size),
                    mtime=float(st.st_mtime),
                ))
            except Exception:
                continue
        # Directories first, then files by name
        items.sort(key=lambda e: (0 if e.type == "folder" else 1, e.name.lower()))
        return {"entries": [asdict(e) for e in items]}

    def get_entry(self, entry_id: str) -> Entry:
        p = self._norm(entry_id)
        st = p.stat()
        return Entry(id=str(p), name=p.name or str(p), type="folder" if p.is_dir() else "file", size=0 if p.is_dir() else int(st.st_size), mtime=float(st.st_mtime))

    def open(self, entry_id: str):
        return open(self._norm(entry_id), 'rb')

    def resolve_scan_target(self, input: Dict) -> Dict:
        path = str(self._norm(input.get('path') or '/'))
        root_id = input.get('root_id') or '/'
        return {"provider_id": self.id, "root_id": root_id, "path": path, "label": path}

    def enumerate_files(self, scan_target: Dict, recursive: bool, progress_cb: Optional[Callable[[int], None]] = None) -> Iterator[Path]:
        base = self._norm(scan_target.get('path') or '/')
        it = base.rglob('*') if recursive else base.glob('*')
        count = 0
        for p in it:
            if p.is_file():
                yield p
                count += 1
                if progress_cb and (count % 100 == 0):
                    progress_cb(count)


class MountedFSProvider(FilesystemProvider):
    id = "mounted_fs"
    display_name = "Mounted Volumes"

    def list_roots(self) -> List[DriveInfo]:
        drives: List[DriveInfo] = []
        # Fallback if psutil missing
        if psutil is None:
            # Use common mount points heuristically
            for p in ["/mnt", "/media", "/Volumes"]:
                pp = Path(p)
                if pp.exists() and pp.is_dir():
                    for child in pp.iterdir():
                        try:
                            if child.is_dir():
                                drives.append(DriveInfo(id=str(child), name=child.name, path=str(child)))
                        except Exception:
                            continue
            return drives
        try:
            parts = psutil.disk_partitions(all=False)
            seen = set()
            for part in parts:
                mount = part.mountpoint
                if mount and mount not in seen:
                    seen.add(mount)
                    drives.append(DriveInfo(id=mount, name=os.path.basename(mount) or mount, path=mount))
        except Exception:
            pass
        return drives

    def list(self, root_id: str, path: str, page_token: Optional[str] = None, page_size: Optional[int] = None) -> Dict:
        # Treat path under selected mount root; if path is empty, list the root itself
        base = Path(path or root_id).resolve()
        if not base.exists():
            return {"entries": []}
        items: List[Entry] = []
        for child in base.iterdir():
            try:
                st = child.stat()
                items.append(Entry(
                    id=str(child.resolve()),
                    name=child.name or str(child),
                    type="folder" if child.is_dir() else "file",
                    size=0 if child.is_dir() else int(st.st_size),
                    mtime=float(st.st_mtime),
                ))
            except Exception:
                continue
        items.sort(key=lambda e: (0 if e.type == "folder" else 1, e.name.lower()))
        return {"entries": [asdict(e) for e in items]}

    def get_entry(self, entry_id: str) -> Entry:
        p = Path(entry_id).resolve()
        st = p.stat()
        return Entry(id=str(p), name=p.name or str(p), type="folder" if p.is_dir() else "file", size=0 if p.is_dir() else int(st.st_size), mtime=float(st.st_mtime))

    def open(self, entry_id: str):
        return open(Path(entry_id).resolve(), 'rb')

    def resolve_scan_target(self, input: Dict) -> Dict:
        root_id = input.get('root_id') or '/'
        path = str(Path(input.get('path') or root_id).resolve())
        return {"provider_id": self.id, "root_id": root_id, "path": path, "label": path}

    def enumerate_files(self, scan_target: Dict, recursive: bool, progress_cb: Optional[Callable[[int], None]] = None) -> Iterator[Path]:
        base = Path(scan_target.get('path') or scan_target.get('root_id') or '/').resolve()
        it = base.rglob('*') if recursive else base.glob('*')
        count = 0
        for p in it:
            if p.is_file():
                yield p
                count += 1
                if progress_cb and (count % 100 == 0):
                    progress_cb(count)


class ProviderRegistry:
    def __init__(self, enabled: Optional[List[str]] = None):
        self.providers: Dict[str, FilesystemProvider] = {}
        if enabled is not None:
            self.enabled = [pid.strip() for pid in enabled if pid.strip()]
        else:
            env = os.environ.get('SCIDK_PROVIDERS', 'local_fs,mounted_fs')
            self.enabled = [p.strip() for p in (env.split(',') if env else []) if p.strip()]

    def register(self, provider: FilesystemProvider):
        if provider.id and (provider.id in self.enabled):
            self.providers[provider.id] = provider

    def get(self, id: str) -> Optional[FilesystemProvider]:
        return self.providers.get(id)

    def list(self) -> List[ProviderDescriptor]:
        return [p.descriptor() for p in self.providers.values()]
