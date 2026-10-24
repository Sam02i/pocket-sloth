"""Build one markdown results table from several metrics .json files.

Usage: uv run python eval/make_table.py "Regex + lookup=results/regex_gold.json" "Qwen3.5-4B zero-shot=results/base4b_zeroshot_gold.json" ...
"""
import json, sys

SLICES = [("seen", "Seen"), ("unseen", "Unseen"), ("noisy", "Noisy"), ("hinglish", "Hinglish"), ("not_txn", "Not-a-txn")]
pct = lambda x: "-" if x is None else f"{x*100:.1f}%"

rows = []
for arg in sys.argv[1:]:
    name, path = arg.rsplit("=", 1)
    m = json.load(open(path))
    a = m["ALL"]; f = a["field_accuracy"]
    rows.append([name, pct(a["json_valid"]), pct(a["row_accuracy"]), pct(a["objective_row_accuracy"]),
                pct(f.get("merchant")), pct(f.get("category")), str(a["false_positives"]), str(a["missed_transactions"])]
                + [pct(m[k]["row_accuracy"]) if k in m else "-" for k, _ in SLICES])
head = ["System", "JSON valid", "Row acc", "Objective acc", "Merchant", "Category", "False pos", "Missed"] + [n for _, n in SLICES]
print("| " + " | ".join(head) + " |")
print("|" + "---|" * len(head))
for r in rows:
    print("| " + " | ".join(r) + " |")