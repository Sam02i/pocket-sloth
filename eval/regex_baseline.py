"""Regex + lookup baseline for Pocket Sloth.

Written from the training-style formats and the DEV set only. It was never tuned on gold.
Rules only fire on known message families; anything else is called "not a transaction".

Usage:  python eval/regex_baseline.py data/dev.jsonl --out results/regex_dev_preds.jsonl
"""
import re, json, argparse

GRO, FOOD, TRN, SHP, BIL, ENT, HLT, TRV, XFR, INC, OTH = (
    "Groceries", "Food & Delivery", "Transport", "Shopping", "Bills & Utilities",
    "Entertainment", "Health", "Travel", "Transfers", "Income & Refunds", "Other")

# ---- merchant dictionary: (regex on the raw merchant text, clean name, category) ----
DICT = [
    (r"swiggy instamart|instamart", "Swiggy Instamart", GRO),
    (r"swiggy", "Swiggy", FOOD), (r"zomato", "Zomato", FOOD), (r"dineout", "Dineout", FOOD),
    (r"starbucks", "Starbucks", FOOD), (r"chai point", "Chai Point", FOOD),
    (r"blinkit", "Blinkit", GRO), (r"zepto", "Zepto", GRO), (r"bigbasket", "BigBasket", GRO),
    (r"reliance smart", "Reliance Smart", GRO),
    (r"uber", "Uber", TRN), (r"\bola\b", "Ola", TRN), (r"rapido", "Rapido", TRN),
    (r"delhi metro", "Delhi Metro", TRN), (r"indian oil", "Indian Oil", TRN), (r"shell", "Shell", TRN),
    (r"amzn|amazon", "Amazon", SHP), (r"flipkart", "Flipkart", SHP), (r"myntra", "Myntra", SHP),
    (r"ajio", "Ajio", SHP), (r"nykaa", "Nykaa", SHP), (r"meesho", "Meesho", SHP),
    (r"decathlon", "Decathlon", SHP),
    (r"airtel", "Airtel", BIL), (r"\bjio\b", "Jio", BIL), (r"bescom", "Bescom", BIL),
    (r"netflix", "Netflix", ENT), (r"spotify", "Spotify", ENT), (r"hotstar", "Hotstar", ENT),
    (r"prime video", "Prime Video", ENT), (r"bookmyshow", "BookMyShow", ENT),
    (r"apollo pharmacy", "Apollo Pharmacy", HLT), (r"netmeds", "Netmeds", HLT), (r"practo", "Practo", HLT),
    (r"makemytrip", "MakeMyTrip", TRV), (r"air india", "Air India", TRV), (r"taj hotels", "Taj Hotels", TRV),
]
RAILS = {"amazon pay": "Amazon Pay", "google pay": "Google Pay", "phonepe": "PhonePe", "paytm": "Paytm"}
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def parse_date(t):
    m = re.search(r"\b(\d{2})[-/](\d{2})[-/](\d{4})\b", t)
    if m:
        d, mo, y = m.groups(); return f"{y}-{mo}-{d}"
    m = re.search(r"\b(\d{2})-?([A-Za-z]{3})-?(\d{2})\b", t)
    if m and m.group(2).lower() in MONTHS:
        d, mo, y = m.groups(); return f"20{y}-{MONTHS[mo.lower()]:02d}-{d}"
    m = re.search(r"\b(\d{2})[-/](\d{2})[-/](\d{2})\b", t)
    if m:
        d, mo, y = m.groups(); return f"20{y}-{mo}-{d}"
    return None


def parse_amount(low):
    m = re.search(r"\b(?:rs\.?|inr|usd)\s?([\d,]+(?:\.\d+)?)", low)
    return float(m.group(1).replace(",", "")) if m else None


def clean_merchant(raw):
    """Dictionary lookup first; otherwise strip noise and Title Case. Returns (name, category)."""
    low = raw.lower()
    for pat, name, cat in DICT:
        if re.search(pat, low):
            return name, cat
    s = raw
    s = re.sub(r"^UPI[-/](?:(?:DR|CR)/)?\d*[-/]?", "", s, flags=re.I)
    s = re.sub(r"^POS \d+ ", "", s, flags=re.I)
    s = re.sub(r"@\S+", "", s)
    s = re.sub(r"[-/ ]?ref ?\d+", "", s, flags=re.I)
    s = re.sub(r"\*ORD \d+", "", s, flags=re.I)
    s = re.sub(r"\b(PVT LTD|LTD|PRIVATE LIMITED)\b", "", s, flags=re.I)
    s = re.sub(r"\s+\d+$", "", s).strip(" -/.*")
    return (s.title() if s else None), OTH


def bank_name(msg):
    m = re.match(r"([A-Za-z ]+?):", msg.strip())
    return m.group(1).title() if m else None


def txn(merchant, amount, direction, date, category, cur="INR"):
    return {"is_transaction": True, "merchant": merchant, "amount": amount, "currency": cur,
            "direction": direction, "date": date, "category": category}


def predict(msg):
    t = msg.strip(); low = t.lower()
    amt = parse_amount(low); date = parse_date(t)
    cur = "USD" if re.search(r"\busd\b", low) else "INR"
    NOT = {"is_transaction": False}

    # ---- family gates: if none matches, we call it "not a transaction" ----
    maple = low.startswith("maple bank:") and re.search(r"rs\.? ?[\d,.]+ (debited from|credited to|withdrawn)", low)
    banyan = low.startswith("banyan bank:") and re.search(r"(inr|usd) [\d,.]+ (spent on card|credited to card)", low)
    lotus = re.match(r"^rs [\d,.]+ (sent to|received from) .+ via lotus pay upi", low) or \
        re.match(r"^rs [\d,.]+ added to .+ wallet", low)
    cedar = re.match(r"^rs\.[\d,.]+ (dr|cr)\. to cedar card", low)
    rail = re.match(r"^(?:you )?paid rs\.? ?[\d,.]+ (?:via|using) (amazon pay|google pay|phonepe|paytm)", low)
    hing = re.search(r"debit hue|credit hue|kat gaye|bheje|nikaale|nikala", low) and \
        not re.search(r"otp|offer|due", low)
    if not (maple or banyan or lotus or cedar or rail or hing) or amt is None:
        return NOT

    credit = bool(re.search(r"credited to|\bcr\.|received from|credit hue", low))
    direction = "credit" if credit else "debit"

    # ---- special cases ----
    if re.search(r"\batm\b", low) and re.search(r"withdrawn|nikaal|nikala", low):
        return txn("ATM", amt, "debit", date, XFR)
    if re.search(r"own a/c|\(self\)|self transfer|own account", low):
        return txn("Self Transfer", amt, direction, date, XFR)
    w = re.search(r"added to (.+? wallet)", t, re.I)
    if w:
        return txn(w.group(1), amt, "debit", date, XFR)
    if re.search(r"towards .*(fee|charges)|towards emi", low):
        return txn(bank_name(t), amt, "debit", date, BIL)

    # ---- rails: Amazon Pay / Google Pay / ... ----
    if rail:
        p = re.search(r" to (.+?) on ", t, re.I)
        if p:
            name, cat = clean_merchant(p.group(1)); return txn(name, amt, "debit", date, cat)
        return txn(RAILS[rail.group(1)], amt, "debit", date, OTH)

    # ---- Lotus Pay UPI ----
    if lotus:
        s = re.search(r"sent to (.+?) via lotus pay", t, re.I)
        r = re.search(r"received from (.+?) via lotus pay", t, re.I)
        who = (s or r).group(1)
        if r:
            return txn(who, amt, "credit", date, XFR)
        if who != who.upper() and not any(re.search(p, who.lower()) for p, _, _ in DICT):
            return txn(who, amt, "debit", date, XFR)          # mixed-case name = a person
        name, cat = clean_merchant(who); return txn(name, amt, "debit", date, cat)

    # ---- Hinglish (a few common verbs only) ----
    if hing and not (maple or banyan or cedar):
        for pat in (r"ko, (.+?)\.? bal", r"kat gaye (.+?) ke liye", r"hain (.+?) se upi", r"aapne (.+?) ko rs"):
            h = re.search(pat, t, re.I)
            if h:
                who = h.group(1)
                if pat.startswith("hain") or pat.startswith("aapne"):
                    return txn(who, amt, direction, date, XFR)
                name, cat = clean_merchant(who); return txn(name, amt, direction, date, cat)
        return txn(None, amt, direction, date, OTH)

    # ---- credits with an Info: / Refund from ... tail ----
    if credit:
        rf = re.search(r"refund(?: from)? (.+?)(?:\.|$)", t, re.I)
        if rf:
            name, _ = clean_merchant(rf.group(1)); return txn(name, amt, "credit", date, INC)
        sal = re.search(r"salary (.+?)(?:\.|$)", t, re.I)
        if sal:
            return txn(sal.group(1).title(), amt, "credit", date, INC)
        info = re.search(r"info: (.+?)(?:\. avl bal|\.?$)", t, re.I)
        if info and re.search(r"UPI/CR/", info.group(1)):
            return txn(clean_merchant(info.group(1))[0], amt, "credit", date, XFR)
        return txn(None, amt, "credit", date, INC)

    # ---- plain debits: "... at MERCHANT ..." ----
    at = re.search(r"\bat (.+?)(?:\. ?avl bal|\. (?:get|not you|pls)|\s+on \d|\.?$)", t, re.I)
    if at:
        name, cat = clean_merchant(at.group(1)); return txn(name, amt, "debit", date, cat)
    return txn(bank_name(t), amt, "debit", date, OTH)       # no merchant shown


_predict_inner = predict


def predict(msg):  # wrapper: set the currency code the message actually shows
    out = _predict_inner(msg)
    if out.get("is_transaction") and re.search(r"\busd\b", msg.lower()):
        out["currency"] = "USD"
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("infile"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(a.infile, encoding="utf-8") as f, open(a.out, "w", encoding="utf-8") as o:
        for line in f:
            r = json.loads(line)
            o.write(json.dumps({"id": r["id"], "pred": predict(r["message"])}, ensure_ascii=False) + "\n")
    print("wrote", a.out)