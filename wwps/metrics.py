from __future__ import annotations

import time
from collections import defaultdict, deque

WINDOW_SECONDS = 120
LATENCY_SAMPLES = 512
EVENT_LOG_SIZE = 50

started_at = time.time()

counters: dict[str, int] = defaultdict(int)
gauges: dict[str, float] = {}

_endpoint_count: dict[str, int] = defaultdict(int)
_endpoint_errors: dict[str, int] = defaultdict(int)
_endpoint_latency: dict[str, deque] = defaultdict(lambda: deque(maxlen=LATENCY_SAMPLES))

_latency: deque = deque(maxlen=LATENCY_SAMPLES)
_buckets: dict[int, dict[str, int]] = {}
_events: deque = deque(maxlen=EVENT_LOG_SIZE)


def incr(name: str, amount: int = 1):
    counters[name] += amount


def gauge(name: str, value: float):
    gauges[name] = value


def _bucket(second: int) -> dict[str, int]:
    bucket = _buckets.get(second)
    if bucket is None:
        bucket = {"requests": 0, "errors": 0}
        _buckets[second] = bucket
        cutoff = second - WINDOW_SECONDS
        for key in [k for k in _buckets if k < cutoff]:
            del _buckets[key]
    return bucket


def record_request(path: str, duration_ms: float, failed: bool):
    now = int(time.time())
    bucket = _bucket(now)
    bucket["requests"] += 1
    if failed:
        bucket["errors"] += 1

    incr("requests_total")
    if failed:
        incr("requests_failed")

    _latency.append(duration_ms)
    _endpoint_count[path] += 1
    _endpoint_latency[path].append(duration_ms)
    if failed:
        _endpoint_errors[path] += 1


def event(level: str, message: str):
    _events.appendleft({"ts": time.time(), "level": level, "message": message})


def percentile(samples, pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[index]


def series(window: int = 60) -> list[dict]:
    now = int(time.time())
    out = []
    for second in range(now - window + 1, now + 1):
        bucket = _buckets.get(second) or {"requests": 0, "errors": 0}
        out.append({
            "t": second,
            "requests": bucket["requests"],
            "errors": bucket["errors"],
        })
    return out


def endpoints(limit: int = 12) -> list[dict]:
    rows = []
    for path, count in _endpoint_count.items():
        samples = _endpoint_latency[path]
        rows.append({
            "path": path,
            "count": count,
            "errors": _endpoint_errors[path],
            "p50": round(percentile(samples, 50), 1),
            "p95": round(percentile(samples, 95), 1),
        })
    rows.sort(key=lambda row: row["count"], reverse=True)
    return rows[:limit]


def rate_per_minute() -> float:
    recent = series(60)
    return sum(row["requests"] for row in recent)


def snapshot() -> dict:
    total = counters["requests_total"]
    failed = counters["requests_failed"]
    return {
        "uptime_seconds": int(time.time() - started_at),
        "requests_total": total,
        "requests_failed": failed,
        "error_rate": round((failed / total * 100.0) if total else 0.0, 2),
        "rate_per_minute": rate_per_minute(),
        "latency_p50": round(percentile(_latency, 50), 1),
        "latency_p95": round(percentile(_latency, 95), 1),
        "latency_p99": round(percentile(_latency, 99), 1),
        "counters": dict(counters),
        "gauges": dict(gauges),
        "series": series(60),
        "endpoints": endpoints(),
        "events": list(_events),
    }


def prometheus() -> str:
    lines = [
        "# TYPE wwps_uptime_seconds gauge",
        f"wwps_uptime_seconds {int(time.time() - started_at)}",
        "# TYPE wwps_requests_total counter",
        f"wwps_requests_total {counters['requests_total']}",
        "# TYPE wwps_requests_failed_total counter",
        f"wwps_requests_failed_total {counters['requests_failed']}",
        "# TYPE wwps_request_latency_ms summary",
        f'wwps_request_latency_ms{{quantile="0.5"}} {percentile(_latency, 50):.1f}',
        f'wwps_request_latency_ms{{quantile="0.95"}} {percentile(_latency, 95):.1f}',
        f'wwps_request_latency_ms{{quantile="0.99"}} {percentile(_latency, 99):.1f}',
    ]
    for name, value in sorted(counters.items()):
        if name in ("requests_total", "requests_failed"):
            continue
        lines.append(f"# TYPE wwps_{name} counter")
        lines.append(f"wwps_{name} {value}")
    for name, value in sorted(gauges.items()):
        lines.append(f"# TYPE wwps_{name} gauge")
        lines.append(f"wwps_{name} {value}")
    for row in endpoints(50):
        label = row["path"].replace('"', "")
        lines.append(f'wwps_endpoint_requests_total{{path="{label}"}} {row["count"]}')
        lines.append(f'wwps_endpoint_errors_total{{path="{label}"}} {row["errors"]}')
        lines.append(f'wwps_endpoint_latency_p95_ms{{path="{label}"}} {row["p95"]}')
    return "\n".join(lines) + "\n"


def reset():
    counters.clear()
    gauges.clear()
    _endpoint_count.clear()
    _endpoint_errors.clear()
    _endpoint_latency.clear()
    _latency.clear()
    _buckets.clear()
    _events.clear()
