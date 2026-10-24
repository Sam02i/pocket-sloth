"""Print only the rows a system got wrong, with exactly which fields differ.

Usage: uv run python eval/show_errors.py results/base4b_zeroshot_dev_preds.jsonl data/dev.jsonl
       add --field merchant   to show only rows where that field is wrong
"""
import json, argparse
from collections import Counter
from metrics import FIELDS, same

ap = argparse.ArgumentParser()
ap.add_argument("preds"); ap.add_argument("data")
ap.add_argument("--field", choices=FIELDS)
a = ap.parse_args()

gold = {r["id"]: r for r in map(json.loads, open(a.data, encoding="utf-8"))}
wrong_fields, shown, total_wrong = Counter(), 0, 0
for line in open(a.preds, encoding="utf-8"):
    r = json.loads(line); g = gold[r["id"]]; p = r["pred"]; gl = g["label"]
    lines = []
    if not isinstance(p, dict) or not isinstance(p.get("is_transaction"), bool):
        lines.append("  INVALID JSON -> " + str(r.get("raw", ""))[:150]); wrong_fields["invalid"] += 1
    elif gl["is_transaction"] and not p["is_transaction"]:
        lines.append("  MISSED: said not-a-transaction"); wrong_fields["missed"] += 1
    elif not gl["is_transaction"] and p["is_transaction"]:
        lines.append("  FALSE POSITIVE: invented a transaction"); wrong_fields["false_positive"] += 1
    elif gl["is_transaction"]:
        for f in FIELDS:
            if not same(f, p.get(f), gl.get(f)):
                wrong_fields[f] += 1
                if a.field in (None, f):
                    lines.append(f"  {f}: expected {gl.get(f)!r}   got {p.get(f)!r}")
    if lines:
        total_wrong += 1
        if a.field is None or any(l.strip().startswith(a.field) for l in lines):
            shown += 1
            print(f"{r['id']} [{g.get('slice','')}] {g['message']}")
            print("\n".join(lines)); print()
print(f"rows with any error: {total_wrong}   shown: {shown}")
print("errors by field:", dict(wrong_fields.most_common()))