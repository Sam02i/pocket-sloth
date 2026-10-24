"""Score predictions against labeled data. Works for any system (regex now, models later).

Usage: python eval/metrics.py results/regex_dev_preds.jsonl data/dev.jsonl --out results/regex_dev.json
A prediction of null/non-dict counts as INVALID JSON.
"""
import json, argparse
from collections import defaultdict

FIELDS = ["merchant", "amount", "currency", "direction", "date", "category"]
OBJECTIVE = ["amount", "currency", "direction", "date"]


def same(field, p, g):
    if field == "amount":
        try:
            return abs(float(p) - float(g)) < 0.005
        except (TypeError, ValueError):
            return False
    return p == g


def score(preds, gold):
    G = {g["id"]: g for g in gold}
    buckets = defaultdict(list)
    for pid, pred in preds.items():
        g = G[pid]
        buckets["ALL"].append((pred, g["label"]))
        if "slice" in g:
            buckets[g["slice"]].append((pred, g["label"]))
    out = {}
    for name, items in buckets.items():
        n = len(items)
        valid = sum(1 for p, _ in items if isinstance(p, dict) and isinstance(p.get("is_transaction"), bool))
        tp = fp = fn = tn = 0
        row_ok = obj_ok = 0
        fc = {f: [0, 0] for f in FIELDS}          # [correct, total] over true transactions
        for p, g in items:
            ok_p = isinstance(p, dict) and isinstance(p.get("is_transaction"), bool)
            pt = ok_p and p["is_transaction"]
            gt = g["is_transaction"]
            tp += pt and gt; fp += pt and not gt; fn += (not pt) and gt; tn += (not pt) and not gt
            if not gt:
                row_ok += (ok_p and not pt); obj_ok += (ok_p and not pt)
                continue
            if not pt:
                continue
            oks = {f: same(f, p.get(f), g.get(f)) for f in FIELDS}
            for f in FIELDS:
                fc[f][1] += 1; fc[f][0] += oks[f]
            row_ok += all(oks.values()); obj_ok += all(oks[f] for f in OBJECTIVE)
        # fields for transactions the system missed count as wrong
        for p, g in items:
            if g["is_transaction"] and not (isinstance(p, dict) and p.get("is_transaction") is True):
                for f in FIELDS: fc[f][1] += 1
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out[name] = {"n": n, "json_valid": valid / n, "row_accuracy": row_ok / n,
                    "objective_row_accuracy": obj_ok / n, "txn_precision": prec, "txn_recall": rec,
                    "false_positives": fp, "missed_transactions": fn,
                    "field_accuracy": {f: (c / t if t else None) for f, (c, t) in fc.items()}}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("preds"); ap.add_argument("gold"); ap.add_argument("--out")
    a = ap.parse_args()
    preds = {}
    for l in open(a.preds, encoding="utf-8"):
        r = json.loads(l); preds[r["id"]] = r["pred"]
    gold = [json.loads(l) for l in open(a.gold, encoding="utf-8")]
    res = score(preds, gold)
    for name, m in res.items():
        print(f"\n== {name} (n={m['n']}) ==")
        print(f"  JSON valid        {m['json_valid']:.1%}")
        print(f"  Whole-row acc     {m['row_accuracy']:.1%}   (objective fields only: {m['objective_row_accuracy']:.1%})")
        print(f"  Is-txn precision  {m['txn_precision']:.1%}   recall {m['txn_recall']:.1%}   false positives {m['false_positives']}   missed {m['missed_transactions']}")
        print("  Field accuracy    " + "  ".join(f"{f} {v:.0%}" for f, v in m["field_accuracy"].items() if v is not None))
    if a.out:
        json.dump(res, open(a.out, "w"), indent=2)