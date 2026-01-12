from typing import Any, Dict, List, Optional


def rclone_env(monkeypatch, *, listremotes: Optional[List[str]] = None,
               lsjson_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
               version: str = "rclone v1.62.2"):
    """
    Minimal helper to fake rclone environment for tests by patching environment
    variables that the app reads and by providing predictable outputs for
    subprocess invocations if the app shells out (future extension point).

    Currently this sets SCIDK_RCLONE_VERSION and SCIDK_RCLONE_LISTREMOTES
    to allow parts of the app that probe configuration to behave deterministically.

    Parameters
    - monkeypatch: pytest monkeypatch fixture
    - listremotes: list of remote names (e.g., ["local", "s3", "gdrive"]).
    - lsjson_map: mapping remote_path -> list of lsjson-like dicts (not wired yet).
    - version: version string to inject.
    """
    if listremotes is None:
        listremotes = ["local_fs"]
    monkeypatch.setenv("SCIDK_RCLONE_VERSION", version)
    monkeypatch.setenv("SCIDK_RCLONE_LISTREMOTES", ",".join(listremotes))
    # Future: monkeypatch subprocess.run to return lsjson_map for given args.
    return {
        "version": version,
        "listremotes": listremotes,
        "lsjson_map": lsjson_map or {},
    }
