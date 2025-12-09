import time
from typing import Any, Dict, List, Optional
import os


def _telemetry(app) -> Dict[str, Any]:
    ext = app.extensions.setdefault('scidk', {})
    return ext.setdefault('telemetry', {})


def inc_counter(app, name: str, value: int = 1) -> None:
    tel = _telemetry(app)
    tel[name] = int(tel.get(name, 0)) + int(value)


def record_event_time(app, name: str, ts: Optional[float] = None) -> None:
    tel = _telemetry(app)
    arr = tel.setdefault(name, [])
    if not isinstance(arr, list):
        arr = []
        tel[name] = arr
    arr.append(float(ts or time.time()))
    # keep last 1000 timestamps
    if len(arr) > 1000:
        del arr[: len(arr) - 1000]


def record_latency(app, name: str, seconds: float) -> None:
    tel = _telemetry(app)
    key = f"lat_{name}"
    arr = tel.setdefault(key, [])
    if not isinstance(arr, list):
        arr = []
        tel[key] = arr
    arr.append(float(seconds))
    # keep last N samples
    if len(arr) > 1000:
        del arr[: len(arr) - 1000]


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    k = max(0, min(len(v) - 1, int(round((pct / 100.0) * (len(v) - 1)))))
    return v[k]


def collect_metrics(app) -> Dict[str, Any]:
    tel = _telemetry(app)
    now = time.time()
    # Throughput over last 5 minutes
    starts = tel.get('scan_started_times') or []
    window = 300.0
    recent = [t for t in starts if (now - float(t)) <= window]
    per_min = len(recent) / (window / 60.0) if recent else 0.0
    # Rows ingested total counter
    rows_total = int(tel.get('rows_ingested_total') or 0)
    # Browse latencies percentiles
    bl = tel.get('lat_browse') or []
    p50 = _percentile(bl, 50.0)
    p95 = _percentile(bl, 95.0)
    # Outbox lag placeholder (only if projection enabled)
    projection_enabled = (str(app.config.get('projection.enableNeo4j') or os.environ.get('SCIDK_FEATURE_NEO4J_OUTBOX') or '')).strip().lower() in ('1','true','yes','y','on')
    outbox_lag = None
    if projection_enabled:
        outbox_lag = 0
    return {
        'scan_throughput_per_min': per_min,
        'rows_ingested_total': rows_total,
        'browse_latency_p50': p50,
        'browse_latency_p95': p95,
        'outbox_lag': outbox_lag,
    }
