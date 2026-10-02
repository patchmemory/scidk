"""
lwm_colab.py: run a private Neo4j inside a Google Colab session and load the study graph.

    from lwm_colab import start_neo4j
    start_neo4j()        # about 2 minutes: Java, Neo4j Community, then the demo graph

Each Colab user gets their own database on their own Colab machine, so there is nothing to
share, no VPN and no tunnel. The database disappears when the Colab session ends.
Works on any Linux machine with apt and sudo-free root (Colab runs as root).
"""
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

NEO4J_VERSION = os.environ.get("NEO4J_VERSION", "5.26.0")
HOME = Path(os.environ.get("NEO4J_LOCAL_HOME", "/content/neo4j"))
PASSWORD = "lwm-colab-local"      # local to this Colab machine; nothing outside can reach it
JAVA_PKG = "openjdk-17-jre-headless"


def _port_open(port=7687, host="127.0.0.1"):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def _run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))} failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.stdout


def _java_home():
    for p in sorted(Path("/usr/lib/jvm").glob("java-*-openjdk-*")):
        if any(v in p.name for v in ("-17-", "-21-")):
            return str(p)
    return None


def _set_env():
    os.environ.update(NEO4J_URI="bolt://localhost:7687", NEO4J_USER="neo4j", NEO4J_PASSWORD=PASSWORD)


def start_neo4j(version=NEO4J_VERSION, load_graph=True):
    """Install and start Neo4j Community locally, then load the demo graph into it."""
    if _port_open():
        print("Neo4j is already running on this machine.")
        _set_env()
        return
    t0 = time.time()
    if not _java_home():
        print("Installing Java 17 ...")
        _run(["apt-get", "-qq", "update"])
        _run(["apt-get", "-qq", "install", "-y", JAVA_PKG])
    java_home = _java_home()
    if not java_home:
        raise RuntimeError("Java 17 or 21 not found after install")

    home = HOME / f"neo4j-community-{version}"
    if not home.exists():
        print(f"Downloading Neo4j Community {version} ...")
        HOME.mkdir(parents=True, exist_ok=True)
        tgz = HOME / f"neo4j-{version}.tar.gz"
        urllib.request.urlretrieve(f"https://dist.neo4j.org/neo4j-community-{version}-unix.tar.gz", tgz)
        with tarfile.open(tgz) as t:
            try:
                t.extractall(HOME, filter="data")
            except TypeError:          # Python without extraction filters
                t.extractall(HOME)
        tgz.unlink()
        conf = home / "conf" / "neo4j.conf"
        with conf.open("a") as f:      # small memory footprint; Colab has ~12 GB
            f.write("\nserver.memory.heap.initial_size=512m\nserver.memory.heap.max_size=1g\n"
                    "server.memory.pagecache.size=512m\n")
        env = {**os.environ, "JAVA_HOME": java_home}
        _run([str(home / "bin" / "neo4j-admin"), "dbms", "set-initial-password", PASSWORD], env=env)

    print("Starting Neo4j ...")
    _run([str(home / "bin" / "neo4j"), "start"], env={**os.environ, "JAVA_HOME": java_home})
    for _ in range(120):
        if _port_open():
            break
        time.sleep(1)
    else:
        log = home / "logs" / "neo4j.log"
        raise RuntimeError("Neo4j didn't start within 2 minutes:\n"
                           + (log.read_text()[-2000:] if log.exists() else "(no log)"))
    _set_env()

    if load_graph:
        print("Loading the study graph ...")
        if importlib_missing("neo4j"):
            _run([sys.executable, "-m", "pip", "-q", "install", "neo4j"])
        out = _run([sys.executable, "load_demo_graph.py", "--wipe"], env=os.environ.copy(),
                   cwd=Path(__file__).parent)
        print("Study graph loaded.")
    print(f"Local Neo4j ready at bolt://localhost:7687 ({time.time() - t0:.0f} s)")


def importlib_missing(name):
    import importlib.util
    return importlib.util.find_spec(name) is None


def stop_neo4j(version=NEO4J_VERSION):
    home = HOME / f"neo4j-community-{version}"
    if home.exists():
        _run([str(home / "bin" / "neo4j"), "stop"], env={**os.environ, "JAVA_HOME": _java_home() or ""})
        print("Neo4j stopped.")
