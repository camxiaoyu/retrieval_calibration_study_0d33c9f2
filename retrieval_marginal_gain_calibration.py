"""（检索结果的边际增益场景）当检索结果的边际增益出现必要冗余被误判时，结论还站得住吗？用检索与排序质量界定可接受的偏差范围。

测量：检索与排序质量（marginal_gain）；协议：校准研究。
仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

SEP = '\t'
MEASURE_FIELD = 'marginal_gain'
FAILURE_MODE = '必要冗余被误判'


def _read_rows(path: str, limit: int = 0) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if SEP and SEP in line:
                label, _, payload = line.partition(SEP)
                rows.append((label.strip(), payload.strip()))
            else:
                rows.append(("", line.strip()))
            if limit and len(rows) >= limit:
                break
    return rows


def _nums(values: list[str]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except ValueError:
            continue
    return out


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac



def measure_retrieval(rows: list[tuple[str, str]]) -> dict:
    """边际增益：逐条加入结果后的增量收益。"""
    hits = []
    for label, payload in rows:
        hits.append(1 if payload.lower() in ("1", "true", "yes", "hit") else 0)
    out: dict = {"metric": "retrieval", "unit": "比例"}
    if not hits:
        out["marginal_gain"] = None
        return out
    curve = []
    cumulative = 0
    prev = 0.0
    for k, hit in enumerate(hits, start=1):
        cumulative += hit
        gain = round(cumulative / k - prev, 6)
        prev = cumulative / k
        curve.append({"k": k, "cumulative": round(cumulative / k, 6),
                      "marginal_gain": gain})
    useful = [c["k"] for c in curve if c["marginal_gain"] > 0]
    out["marginal_gain"] = curve[-1]["marginal_gain"] if curve else None
    out["useful_depth"] = max(useful) if useful else 0
    out["curve"] = curve
    out["total_precision"] = round(cumulative / len(hits), 4)
    return out



def measure(rows: list[tuple[str, str]]) -> dict:
    """按测量族分派到具体测量函数。"""
    return measure_retrieval(rows)



def run_protocol(measure, rows: list[tuple[str, str]], args: argparse.Namespace) -> dict:
    """校准研究：按分桶比较标称与实测的偏差。"""
    bins = max(2, int(args.bins or 10))
    buckets: list[list[tuple[str, str]]] = [[] for _ in range(bins)]
    for idx, row in enumerate(rows):
        buckets[idx % bins].append(row)
    per_bin = []
    errors = []
    for idx, items in enumerate(buckets):
        if not items:
            continue
        nominal = (idx + 1) / bins
        actual = measure(items).get('marginal_gain')
        if isinstance(actual, (int, float)):
            errors.append(abs(actual - nominal))
            per_bin.append({"bin": idx, "nominal": round(nominal, 4),
                            "actual": round(actual, 4),
                            "gap": round(abs(actual - nominal), 4)})
    mean_error = sum(errors) / len(errors) if errors else None
    return {"protocol": "calibration_study", "bins": per_bin,
            "calibration_error": round(mean_error, 4) if mean_error is not None else None}



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="（检索结果的边际增益场景）当检索结果的边际增益出现必要冗余被误判时，结论还站得住吗？用检索与排序质量界定可接受的偏差范围。")
    ap.add_argument("--input", help="输入文件路径")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 行")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--threshold", type=float, default=0.0, help="判定阈值")
    ap.add_argument("--budget", type=int, default=50, help="预算条数")
    ap.add_argument("--bins", type=int, default=10, help="分桶数量")
    ap.add_argument("--components", default="", help="组件列表（逗号分隔）")
    args = ap.parse_args(argv)

    if not args.input:
        ap.print_help()
        return 0

    t0 = time.time()
    try:
        rows = _read_rows(args.input, args.limit)
    except OSError as exc:
        print(f"读取失败：{exc}", file=sys.stderr)
        return 2

    measured = measure(rows)
    result = run_protocol(measure, rows, args)
    result["measure"] = measured
    result["row_count"] = len(rows)
    result["failure_mode"] = FAILURE_MODE
    result["elapsed_seconds"] = round(time.time() - t0, 4)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        value = measured.get(MEASURE_FIELD)
        print(f"读取 1 个文件，共 {result['row_count']} 条记录")
        print(f"{MEASURE_FIELD} = {value}")
        print(f"处理完成，耗时 {result['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
