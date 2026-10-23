"""
Victim Web Application
======================
Simulates a real-world web service targeted by the DDoS attack.
Intentionally adds processing delay to mimic a realistic workload.

Also exposes GET /metrics so the monitoring API can measure traffic
volume at the HTTP layer — this is used as a fallback when Scapy
cannot capture loopback packets on Windows.

Protection Mode:
  - POST /set-protection { "enabled": true/false }
  - When enabled=False the /api/data endpoint returns HTTP 503
    to simulate the victim app going down under attack.

Run:
    python victim_app/app.py
URL:
    http://localhost:8000
"""

import os
import time
import random
import threading
from collections import Counter
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── HTTP-level traffic tracker ─────────────────────────────────────────
_buf_lock = threading.Lock()
_req_buf: list = []
_last_attack_time: float = 0.0

# ── Protection flag ────────────────────────────────────────────────────
_prot_lock        = threading.Lock()
_protection_on    = True   # True = protected, False = victim is exposed / "down"

# ── Mitigation enforcement state (synced from monitoring API) ──────────
_mitig_lock       = threading.Lock()
_blocked_ips      = set()
_rate_limits      = {}     # ip -> max_req_per_sec
_ip_req_times     = {}     # ip -> list of timestamps
_traffic_shape_on = False

SKIP_PATHS = {"/metrics", "/health", "/", "/set-protection", "/protection-status", "/apply-mitigation", "/clear-mitigation"}


@app.before_request
def _track() -> None:
    """Record every tracked request into the rolling buffer and enforce mitigations."""
    if request.path in SKIP_PATHS:
        return

    # Extract source IP (supports X-Forwarded-For simulation)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        src_ip = forwarded.split(",")[0].strip()
    else:
        src_ip = request.remote_addr or "127.0.0.1"

    now = time.time()

    global _last_attack_time

    # Check for SYN simulation or attack flags
    is_syn = bool(
        request.headers.get("X-Syn-Simulation") == "1"
        or request.headers.get("X-Attack-Type") in ("syn-flood", "slowloris", "conn-reset")
    )
    is_attack_header = bool(
        request.headers.get("X-Attack-Type")
        or request.headers.get("X-Attack-Weight")
        or request.headers.get("X-Syn-Simulation")
    )

    payload_len = request.content_length or 0
    approx_bytes = 200 + len(request.path) + payload_len
    weight = min(int(request.headers.get("X-Attack-Weight", 1)), 100)

    with _buf_lock:
        _prune(6.0)
        for _ in range(weight):
            _req_buf.append({
                "t":   now,
                "ip":  src_ip,
                "b":   approx_bytes,
                "syn": is_syn,
            })
        if is_attack_header or len(_req_buf) >= 10:
            _last_attack_time = now

    # ── Enforcement: Check active mitigations if protection is enabled ──
    with _prot_lock:
        protected = _protection_on

    if protected:
        with _mitig_lock:
            # 1. IP Block: immediately drop / reject with 403 Forbidden
            if src_ip in _blocked_ips:
                return jsonify({
                    "status": "error",
                    "code": 403,
                    "message": f"Access Denied: IP {src_ip} is blocked by mitigation engine"
                }), 403

            # 2. Rate Limit: drop excess requests if rate limit exceeded
            if src_ip in _rate_limits:
                limit = _rate_limits[src_ip]
                reqs = _ip_req_times.setdefault(src_ip, [])
                _ip_req_times[src_ip] = [t for t in reqs if now - t <= 1.0]
                if len(_ip_req_times[src_ip]) >= limit:
                    return jsonify({
                        "status": "error",
                        "code": 429,
                        "message": f"Too Many Requests: IP {src_ip} rate limit of {limit} req/s exceeded"
                    }), 429
                _ip_req_times[src_ip].append(now)

            # 3. Traffic Shaping: drop 50% burst packets
            if _traffic_shape_on and random.random() < 0.5:
                return jsonify({
                    "status": "error",
                    "code": 503,
                    "message": "Traffic Shape: packet dropped due to queue congestion"
                }), 503


def _prune(window: float = 6.0) -> None:
    """Remove entries older than `window` seconds (called under lock)."""
    cutoff = time.time() - window
    while _req_buf and _req_buf[0]["t"] < cutoff:
        _req_buf.pop(0)


def is_under_attack() -> bool:
    """Check if the app is currently overwhelmed by high traffic."""
    with _buf_lock:
        _prune(6.0)
        now = time.time()
        if (now - _last_attack_time) < 5.0:
            return True
        return len(_req_buf) >= 10


@app.after_request
def add_no_cache(response):
    """Prevent browsers from caching old HTML so status updates show immediately."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── Routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main UI page."""
    with _prot_lock:
        protected = _protection_on

    # Goes down ONLY when protection is OFF AND server is actively under attack!
    if not protected and is_under_attack():
        return "503 Service Unavailable", 503, {"Content-Type": "text/plain"}

    return render_template("index.html")


@app.route("/api/data", methods=["GET", "POST", "HEAD"])
def api_data():
    """
    Data API endpoint that simulates real processing work.
    This is the target endpoint for the DDoS attack simulation.
    Goes down ONLY when protection is OFF AND server is actively under attack!
    """
    with _prot_lock:
        protected = _protection_on

    if not protected and is_under_attack():
        return "503 Service Unavailable", 503, {"Content-Type": "text/plain"}

    # Fast response during benchmark/stress test
    delay = random.uniform(0.005, 0.02)
    time.sleep(delay)

    return jsonify({
        "status": "ok",
        "message": "Data processed successfully",
        "processing_time_ms": round(delay * 1000, 2),
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data": {
            "id":        random.randint(1000, 9999),
            "metric_a":  round(random.uniform(0, 100), 2),
            "metric_b":  round(random.gauss(50, 15), 2),
            "timestamp": time.time(),
        },
    })


@app.route("/metrics")
def metrics():
    """
    Traffic metrics for the last 3-second window.
    Called by the monitoring API as a fallback when Scapy
    cannot capture loopback packets on Windows.
    """
    window = 3.0
    now    = time.time()

    with _buf_lock:
        _prune(window * 2)
        recent = [r for r in _req_buf if now - r["t"] <= window]
        # Rolling window is maintained by _prune; do not wipe out buffer

    ips       = Counter(r["ip"] for r in recent)
    top_ip    = ips.most_common(1)[0][0] if ips else None
    n_bytes   = sum(r["b"] for r in recent)
    syn_count = sum(1 for r in recent if r.get("syn"))
    syn_ratio = (syn_count / len(recent)) if recent else 0.0

    return jsonify({
        "count":      len(recent),
        "bytes":      n_bytes,
        "unique_ips": len(ips),
        "syn_ratio":  round(syn_ratio, 4),
        "top_ip":     top_ip,
        "window_sec": window,
    })


@app.route("/health")
def health():
    """Health check endpoint."""
    with _prot_lock:
        protected = _protection_on
    return jsonify({
        "status":     "healthy" if protected else "degraded",
        "protected":  protected,
        "timestamp":  time.time(),
    })


@app.route("/set-protection", methods=["GET", "POST"])
def set_protection():
    """
    Called by the monitoring API when the dashboard protection switch changes.
    Body: { "enabled": true | false } or GET query: ?enabled=false
    """
    global _protection_on
    enabled = True
    try:
        if request.is_json or request.data:
            body = request.get_json(force=True, silent=True) or {}
            if "enabled" in body:
                enabled = bool(body["enabled"])
        if "enabled" in request.args:
            enabled = request.args.get("enabled", "true").lower() in ("true", "1")
        if request.form and "enabled" in request.form:
            enabled = request.form.get("enabled", "true").lower() in ("true", "1")
    except Exception:
        pass

    with _prot_lock:
        _protection_on = enabled

    state = "ENABLED" if enabled else "DISABLED"
    print(f"[Victim] Protection {state}")
    return jsonify({"protection": enabled, "message": f"Protection {state}"})


@app.route("/protection-status")
def protection_status():
    """Return current protection state."""
    with _prot_lock:
        protected = _protection_on
    return jsonify({"protection_enabled": protected})


@app.route("/apply-mitigation", methods=["POST"])
def apply_mitigation_endpoint():
    """
    Called by monitoring API to sync mitigation rules to the victim server.
    Body: { "type": "ip_block"|"rate_limit"|"traffic_shape"|"geo_block", "ip": "...", "limit": 15 }
    """
    import json as _json
    data = _json.loads(request.data or b"{}")
    m_type = data.get("type")
    ip     = data.get("ip")
    limit  = data.get("limit", 15)

    with _mitig_lock:
        if m_type in ("ip_block", "geo_block"):
            if ip:
                _blocked_ips.add(ip)
                print(f"[Victim Enforce] Blocked IP: {ip}")
        elif m_type == "rate_limit":
            if ip:
                _rate_limits[ip] = limit
                print(f"[Victim Enforce] Rate limit IP {ip} -> {limit} req/s")
        elif m_type == "traffic_shape":
            global _traffic_shape_on
            _traffic_shape_on = True
            print("[Victim Enforce] Traffic shaping active")

    return jsonify({"status": "applied", "type": m_type, "ip": ip})


@app.route("/clear-mitigation", methods=["POST"])
def clear_mitigation_endpoint():
    """Clear all active mitigation rules (called on reset)."""
    global _traffic_shape_on
    with _mitig_lock:
        _blocked_ips.clear()
        _rate_limits.clear()
        _ip_req_times.clear()
        _traffic_shape_on = False
    print("[Victim Enforce] All mitigations cleared")
    return jsonify({"status": "cleared"})


# ── Entry Point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("=" * 52)
    print("  Victim Web App")
    print(f"  Port             : {port}")
    print(f"  Homepage         : http://localhost:{port}")
    print(f"  API              : http://localhost:{port}/api/data")
    print(f"  Metrics          : http://localhost:{port}/metrics")
    print(f"  Health           : http://localhost:{port}/health")
    print("  Protection Toggle: POST /set-protection")
    print("=" * 52)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
