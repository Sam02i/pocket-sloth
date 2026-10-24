"""Send labeled messages to a model on Tinker and save its predictions.

Examples (run from the project folder):
uv run python eval/run_eval.py --model Qwen/Qwen3.5-4B --mode zeroshot --data data/dev.jsonl \
    --out results/base4b_zeroshot_dev_preds.jsonl --limit 5
uv run python eval/run_eval.py --model Qwen/Qwen3.5-4B --mode fewshot  --data data/dev.jsonl \
    --out results/base4b_fewshot_dev_preds.jsonl

Rules: thinking is always OFF. Few-shot examples come from DEV only, never from gold.
"""
import argparse, asyncio, json, re, sys, time

SYSTEM_FULL = """You convert ONE bank, UPI or card alert message into a JSON object. Reply with JSON only, no explanation.

If money did not actually move, reply exactly {"is_transaction": false}. That covers: OTPs, promos and offers, balance-only or limit-only alerts, failed payments where nothing was debited, payment requests, bills or dues reminders, login / card-block / KYC / statement notices, and "payment failed, amount will be reversed later" notices.

Otherwise reply with these keys: is_transaction (true), merchant, amount, currency, direction, date, category.
- amount: a plain number for THIS transaction (no commas, no symbols). Never the balance or limit.
- currency: "INR" unless the message clearly says another currency such as "USD".
- direction: "debit" if money left the account, "credit" if money came in. Refunds are credits.
- date: YYYY-MM-DD. Dates are day-first and two-digit years mean 20xx. If the message has no date, use null. Never guess.
- merchant: the clean everyday name in Title Case. Remove reference numbers, order IDs, asterisks, UPI prefixes and endings like PVT LTD. For people, keep the name as written in Title Case. Sub-brands are separate merchants (Swiggy Instamart is not Swiggy). Amazon Pay, Google Pay, PhonePe and Paytm are only ways of paying: use who was paid, and if no payee is named the merchant is the app and the category is Other. ATM withdrawal: merchant "ATM". Own-account transfer: merchant "Self Transfer". If no merchant is shown, use the bank name.
- category: exactly one of Food & Delivery, Groceries, Transport, Shopping, Bills & Utilities, Entertainment, Health, Travel, Transfers, Income & Refunds, Other. Category follows what the merchant mainly is, not what was bought. Credits are Income & Refunds, except money to or from a person, which is Transfers. ATM, self-transfers, wallet top-ups and person-to-person payments are Transfers. Bank fees and EMIs are Bills & Utilities. Generic shop names or unclear cases are Other."""

SYSTEM_MINIMAL = "Convert the alert message into a JSON object."

FEWSHOT_DEV_IDS = ["d001", "d004", "d005", "d009", "d010", "d012", "d020", "d039", "d041", "d045", "d049"]


def build_messages(mode, prompt, message, shots):
    sys_text = SYSTEM_MINIMAL if prompt == "minimal" else SYSTEM_FULL
    msgs = [{"role": "system", "content": sys_text}]
    if mode == "fewshot":
        for s in shots:
            msgs.append({"role": "user", "content": s["message"]})
            msgs.append({"role": "assistant", "content": json.dumps(s["label"], ensure_ascii=False)})
    msgs.append({"role": "user", "content": message})
    return msgs


def parse_output(text):
    """Return a dict, or None if the reply is not valid JSON."""
    t = text.strip()
    if "</think>" in t:
        t = t.split("</think>")[-1].strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t).strip()
    for cand in (t, (re.search(r"\{.*\}", t, re.S) or [None])[0] if re.search(r"\{.*\}", t, re.S) else None):
        if not cand:
            continue
        try:
            obj = json.loads(cand)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="Tinker base model id, e.g. Qwen/Qwen3.5-4B")
    ap.add_argument("--model-path", help="tinker://... checkpoint path (for the fine-tuned model)")
    ap.add_argument("--mode", choices=["zeroshot", "fewshot"], default="zeroshot")
    ap.add_argument("--prompt", choices=["full", "minimal"], default="full")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None, help="only the first N rows (smoke test)")
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()
    if not (a.model or a.model_path):
        sys.exit("Give --model or --model-path")

    import tinker
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8")]
    if a.limit:
        rows = rows[:a.limit]
    shots = []
    if a.mode == "fewshot":
        dev = {r["id"]: r for r in map(json.loads, open("data/dev.jsonl", encoding="utf-8"))}
        shots = [dev[i] for i in FEWSHOT_DEV_IDS]

    service = tinker.ServiceClient(display_name="pocket-sloth-eval")
    client = await (service.create_sampling_client_async(model_path=a.model_path) if a.model_path
                    else service.create_sampling_client_async(base_model=a.model))
    tok = client.get_tokenizer()
    params = tinker.types.SamplingParams(max_tokens=256, temperature=0.0)
    sem = asyncio.Semaphore(a.concurrency)

    async def one(r):
        msgs = build_messages(a.mode, a.prompt, r["message"], shots)
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=False, return_dict=False)
        for attempt in range(3):
            try:
                async with sem:
                    t0 = time.perf_counter()
                    res = await client.sample_async(prompt=tinker.types.ModelInput.from_ints(ids),
                                                    num_samples=1, sampling_params=params)
                    dt = time.perf_counter() - t0
                seq = res.sequences[0]
                raw = tok.decode(seq.tokens, skip_special_tokens=True)
                return {"id": r["id"], "pred": parse_output(raw), "raw": raw, "latency_s": round(dt, 3),
                        "prompt_tokens": len(ids), "completion_tokens": len(seq.tokens),
                        "stop_reason": str(seq.stop_reason)}
            except Exception as e:                      # retry a couple of times, then record the error
                err = repr(e)
                await asyncio.sleep(2)
        return {"id": r["id"], "pred": None, "raw": "ERROR: " + err, "latency_s": None,
                "prompt_tokens": len(ids), "completion_tokens": 0, "stop_reason": "error"}

    results = await asyncio.gather(*[one(r) for r in rows])
    with open(a.out, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(results)
    invalid = sum(r["pred"] is None for r in results)
    leaks = sum("<think>" in r["raw"] for r in results)
    errors = sum(r["stop_reason"] == "error" for r in results)
    cut = sum("length" in r["stop_reason"] for r in results)
    lat = sorted(r["latency_s"] for r in results if r["latency_s"] is not None)
    print(f"\nwrote {a.out}  ({n} messages)")
    print(f"invalid JSON: {invalid}   thinking leaks: {leaks}   errors: {errors}   cut off: {cut}")
    if lat:
        print(f"Tinker latency per message (network included, NOT the Mac number): p50 {lat[len(lat)//2]:.2f}s  p95 {lat[int(len(lat)*0.95)-1]:.2f}s")
    print(f"tokens: prompt {sum(r['prompt_tokens'] for r in results)}  completion {sum(r['completion_tokens'] for r in results)}")
    print("\nNext: uv run python eval/metrics.py", a.out, a.data)


if __name__ == "__main__":
    asyncio.run(main())