"""Build a static 6-panel HTML dashboard from data/logs.jsonl per config/dashboard.yaml."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
OPS = {"lte": lambda v, t: v <= t, "gte": lambda v, t: v >= t}


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def load(path: Path, minutes: int) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            r["_t"] = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
            rows.append(r)
        except (ValueError, KeyError):
            continue
    if not rows:
        return rows
    end = max(r["_t"] for r in rows)
    return [r for r in rows if r["_t"] >= end - timedelta(minutes=minutes)]


def by_minute(rows: list[dict], field: str | None) -> list[tuple[str, float]]:
    agg: dict[str, float] = defaultdict(float)
    for r in rows:
        agg[r["_t"].strftime("%H:%M")] += r.get(field, 0) if field else 1
    return sorted(agg.items())


def spark(points: list[tuple[str, float]], threshold: float | None, w=420, h=110) -> str:
    if not points:
        return "<p>no data</p>"
    vals = [v for _, v in points]
    top = max(vals + ([threshold] if threshold else [])) * 1.1 or 1
    n = max(len(points) - 1, 1)
    xy = [(30 + i * (w - 40) / n, h - 15 - v / top * (h - 25)) for i, (_, v) in enumerate(points)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    thr = ""
    if threshold:
        y = h - 15 - threshold / top * (h - 25)
        thr = f'<line x1="30" x2="{w-10}" y1="{y:.1f}" y2="{y:.1f}" stroke="#d33" stroke-dasharray="4"/><text x="32" y="{y-3:.1f}" fill="#d33" font-size="10">threshold {threshold}</text>'
    return (f'<svg viewBox="0 0 {w} {h}" width="100%">{thr}<polyline fill="none" stroke="#2a6" stroke-width="2" points="{line}"/>'
            f'<text x="2" y="12" font-size="10">{top:.3g}</text><text x="2" y="{h-15}" font-size="10">0</text>'
            f'<text x="30" y="{h-2}" font-size="10">{points[0][0]}</text><text x="{w-45}" y="{h-2}" font-size="10">{points[-1][0]}</text></svg>')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="data/logs.jsonl")
    ap.add_argument("--out", default="dashboard/dashboard.html")
    ap.add_argument("--minutes", type=int, default=None, help="override time range")
    a = ap.parse_args()
    cfg = yaml.safe_load((REPO_ROOT / "config/dashboard.yaml").read_text(encoding="utf-8"))["dashboard"]
    minutes = a.minutes or cfg["time_range_minutes"]
    rows = load(REPO_ROOT / a.logs, minutes)
    resp = [r for r in rows if r.get("event") == "response_sent"]
    req = [r for r in rows if r.get("event") == "request_received"]
    fail = [r for r in rows if r.get("event") == "request_failed"]
    lat = [r["latency_ms"] for r in resp]
    ttft = [r["ttft_ms"] for r in resp]
    tool = [r["tool_success"] for r in rows if r.get("tool_success") is not None]
    ts = [r["_t"] for r in rows]
    span_min = max((max(ts) - min(ts)).total_seconds() / 60, 1) if ts else 1

    m = {
        "latency": {"p50": pct(lat, 50), "p95": pct(lat, 95), "p99": pct(lat, 99), "ttft_p95": pct(ttft, 95)},
        "traffic": {"count": len(req), "rate_per_minute": len(req) / span_min},
        "errors": {"error_rate_pct": len(fail) / len(req) * 100 if req else 0.0,
                   "tool_success_rate_pct": sum(tool) / len(tool) * 100 if tool else 100.0},
        "cost": {"total": sum(r["cost_usd"] for r in resp)},
        "tokens": {"sum_by_field": sum(r["tokens_in"] + r["tokens_out"] for r in resp)},
        "quality": {"mean": sum(r["quality_score"] for r in resp) / len(resp) if resp else 0.0},
    }
    series = {
        "latency": [(t, v) for t, v in by_minute(resp, "latency_ms")],
        "traffic": by_minute(req, None),
        "errors": by_minute(fail, None),
        "cost": by_minute(resp, "cost_usd"),
        "tokens": by_minute(resp, "tokens_out"),
        "quality": by_minute(resp, "quality_score"),
    }
    # latency/quality series are per-minute means, not sums
    for key, field in (("latency", "latency_ms"), ("quality", "quality_score")):
        c = Counter(r["_t"].strftime("%H:%M") for r in resp)
        series[key] = [(t, v / c[t]) for t, v in series[key]]

    cards = []
    for p in cfg["panels"]:
        th = p["threshold"]
        val = m[p["id"]][th["aggregation"]]
        ok = OPS[th["operator"]](val, th["value"])
        extra = ""
        if p["id"] == "latency":
            l = m["latency"]
            extra = f'P50 {l["p50"]:.0f} | P95 {l["p95"]:.0f} | P99 {l["p99"]:.0f} | TTFT P95 {l["ttft_p95"]:.0f} ms'
        elif p["id"] == "errors":
            ec = Counter(r.get("error_type", "?") for r in fail)
            extra = f'retrieval success {m["errors"]["tool_success_rate_pct"]:.1f}% | by type: {dict(ec) or "none"}'
        elif p["id"] == "tokens":
            extra = f'in {sum(r["tokens_in"] for r in resp)} | out {sum(r["tokens_out"] for r in resp)}'
        elif p["id"] == "traffic":
            extra = f'{m["traffic"]["count"]} requests'
        thr_line = th["value"] if p["id"] in ("latency", "cost", "quality") else None
        cards.append(
            f'<section class="{"ok" if ok else "bad"}"><h2>{escape(p["title"])}</h2>'
            f'<div class="big">{val:.4g} <small>{escape(p["unit"])}</small></div>'
            f'<div>{escape(extra)}</div>{spark(series[p["id"]], thr_line if p["id"] != "cost" else None)}'
            f'<small>{th["aggregation"]} {th["operator"]} {th["value"]} &rarr; {"OK" if ok else "BREACH"}</small></section>')
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    html = (f'<!doctype html><meta charset="utf-8"><title>{escape(cfg["title"])}</title>'
            '<style>body{font:14px sans-serif;background:#111;color:#eee;margin:16px}'
            '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:12px}'
            'section{background:#1c1c1c;border-left:5px solid #2a6;padding:10px;border-radius:6px}'
            'section.bad{border-color:#d33}.big{font-size:26px;font-weight:bold}h2{margin:0 0 6px;font-size:15px}'
            'small{color:#aaa}</style>'
            f'<h1>{escape(cfg["title"])}</h1><p>Time range: last {minutes} min (of data in logs) | '
            f'auto refresh {cfg["refresh_seconds"]}s | generated {now} | records {len(rows)}</p>'
            f'<meta http-equiv="refresh" content="{cfg["refresh_seconds"]}"><div class="grid">{"".join(cards)}</div>')
    out = REPO_ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(rows)} records, {minutes} min)")


if __name__ == "__main__":
    sys.exit(main())
