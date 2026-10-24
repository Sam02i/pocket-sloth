"""Seed generator for Pocket Sloth training data.

Writes alerts from templates in the SIX training formats only (Maple, Banyan, Lotus Pay,
Cedar, Amazon-Pay-style rails, Hinglish). Every label is known exactly and follows
docs/labeling_guide.md. Never uses the gold-only formats (Teak, Willow, Juniper, Aspen),
gold-only merchants, people or employers. Drops anything with the same shape as a gold/dev message.

Usage: python gen/templates.py --n 2400 --seed 7 --out data/seed_raw.jsonl --splits-out data/splits.json
"""
import argparse, json, math, random, re
from collections import Counter
from datetime import date, timedelta

FOOD, GRO, TRN, SHP, BIL, ENT, HLT, TRV, XFR, INC, OTH = (
    "Food & Delivery", "Groceries", "Transport", "Shopping", "Bills & Utilities", "Entertainment",
    "Health", "Travel", "Transfers", "Income & Refunds", "Other")

# canonical name -> (category, [raw names as banks print them])
CATALOG = {
    # Food & Delivery
    "Swiggy": (FOOD, ["SWIGGY"]), "Zomato": (FOOD, ["ZOMATO"]), "Dineout": (FOOD, ["DINEOUT"]),
    "Starbucks": (FOOD, ["STARBUCKS COFFEE", "STARBUCKS"]), "Chai Point": (FOOD, ["CHAI POINT"]),
    "Subway": (FOOD, ["SUBWAY"]), "Burger King": (FOOD, ["BURGER KING"]), "Faasos": (FOOD, ["FAASOS"]),
    "Box8": (FOOD, ["BOX8"]), "Theobroma": (FOOD, ["THEOBROMA"]), "Barista": (FOOD, ["BARISTA COFFEE"]),
    "Pizza Hut": (FOOD, ["PIZZA HUT"]), "Wow Momo": (FOOD, ["WOW MOMO"]), "Keventers": (FOOD, ["KEVENTERS"]),
    "Behrouz Biryani": (FOOD, ["BEHROUZ BIRYANI", "BEHROUZ"]),
    # Groceries
    "Blinkit": (GRO, ["BLINKIT"]), "Zepto": (GRO, ["ZEPTO", "ZEPTO MARKETPLACE"]),
    "BigBasket": (GRO, ["BIGBASKET"]), "Swiggy Instamart": (GRO, ["SWIGGY INSTAMART", "INSTAMART"]),
    "Reliance Smart": (GRO, ["RELIANCE SMART"]), "DMart": (GRO, ["DMART", "AVENUE SUPERMARTS DMART"]),
    "Country Delight": (GRO, ["COUNTRY DELIGHT"]), "Milkbasket": (GRO, ["MILKBASKET"]),
    "JioMart": (GRO, ["JIOMART"]),
    # Transport
    "Uber": (TRN, ["UBER INDIA SYSTEMS", "UBER"]), "Ola": (TRN, ["OLA", "OLA CABS"]),
    "Rapido": (TRN, ["RAPIDO"]), "Delhi Metro": (TRN, ["DELHI METRO"]), "Mumbai Metro": (TRN, ["MUMBAI METRO"]),
    "Indian Oil": (TRN, ["INDIAN OIL FUEL STN", "INDIAN OIL"]), "Shell": (TRN, ["SHELL FUEL STATION", "SHELL"]),
    "Bharat Petroleum": (TRN, ["BHARAT PETROLEUM"]), "Namma Yatri": (TRN, ["NAMMA YATRI"]),
    "ParkPlus": (TRN, ["PARKPLUS"]),
    # Shopping
    "Amazon": (SHP, ["AMZN PAY INDIA", "AMAZON PAY INDIA", "AMAZON SELLER SERVICES", "AMAZON"]),
    "Flipkart": (SHP, ["FLIPKART INTERNET", "FLIPKART"]), "Myntra": (SHP, ["MYNTRA", "MYNTRA DESIGNS"]),
    "Ajio": (SHP, ["AJIO"]), "Nykaa": (SHP, ["NYKAA"]), "Meesho": (SHP, ["MEESHO"]),
    "Decathlon": (SHP, ["DECATHLON SPORTS INDIA", "DECATHLON"]), "Croma": (SHP, ["CROMA"]),
    "Reliance Digital": (SHP, ["RELIANCE DIGITAL"]), "Lenskart": (SHP, ["LENSKART"]),
    "Tata Cliq": (SHP, ["TATA CLIQ"]), "Zara": (SHP, ["ZARA"]), "Pepperfry": (SHP, ["PEPPERFRY"]),
    "Westside": (SHP, ["WESTSIDE"]), "Shoppers Stop": (SHP, ["SHOPPERS STOP"]),
    "Max Fashion": (SHP, ["MAX FASHION"]), "Snapdeal": (SHP, ["SNAPDEAL"]),
    # Bills & Utilities
    "Airtel": (BIL, ["AIRTEL PAYMENTS", "AIRTEL"]), "Jio": (BIL, ["JIO PREPAID RECHARGE", "JIO"]),
    "Bescom": (BIL, ["BESCOM"]), "BSES": (BIL, ["BSES YAMUNA POWER", "BSES RAJDHANI"]),
    "Adani Electricity": (BIL, ["ADANI ELECTRICITY"]), "Indane Gas": (BIL, ["INDANE GAS"]),
    "Hathway": (BIL, ["HATHWAY BROADBAND", "HATHWAY"]), "Tata Play": (BIL, ["TATA PLAY"]),
    "Max Life Insurance": (BIL, ["MAX LIFE INSURANCE"]),
    # Entertainment
    "Netflix": (ENT, ["NETFLIX COM MUMBAI", "NETFLIX COM", "NETFLIX"]), "Spotify": (ENT, ["SPOTIFY"]),
    "Hotstar": (ENT, ["HOTSTAR"]), "Prime Video": (ENT, ["PRIME VIDEO"]), "BookMyShow": (ENT, ["BOOKMYSHOW"]),
    "Zee5": (ENT, ["ZEE5"]), "Steam": (ENT, ["STEAM PURCHASE", "STEAM"]), "PVR Cinemas": (ENT, ["PVR CINEMAS"]),
    # Health
    "Apollo Pharmacy": (HLT, ["APOLLO PHARMACY"]), "Netmeds": (HLT, ["NETMEDS"]), "Practo": (HLT, ["PRACTO"]),
    "PharmEasy": (HLT, ["PHARMEASY"]), "MedPlus": (HLT, ["MEDPLUS HEALTH SERVICES", "MEDPLUS"]),
    "Cult Fit": (HLT, ["CULT FIT"]), "Thyrocare": (HLT, ["THYROCARE"]), "Fortis Hospital": (HLT, ["FORTIS HOSPITAL"]),
    "Healthians": (HLT, ["HEALTHIANS"]),
    # Travel
    "MakeMyTrip": (TRV, ["MAKEMYTRIP"]), "Air India": (TRV, ["AIR INDIA"]), "Taj Hotels": (TRV, ["TAJ HOTELS"]),
    "IndiGo": (TRV, ["INDIGO"]), "Goibibo": (TRV, ["GOIBIBO"]), "Yatra": (TRV, ["YATRA ONLINE", "YATRA"]),
    "OYO": (TRV, ["OYO ROOMS", "OYO"]), "RedBus": (TRV, ["REDBUS"]), "IRCTC": (TRV, ["IRCTC"]),
    "Vistara": (TRV, ["VISTARA"]), "Airbnb": (TRV, ["AIRBNB"]), "EaseMyTrip": (TRV, ["EASEMYTRIP"]),
    # Other (services that fit no category)
    "Urban Company": (OTH, ["URBAN COMPANY"]), "Lakme Salon": (OTH, ["LAKME SALON"]),
    "Naturals Salon": (OTH, ["NATURALS SALON"]), "Green Trends": (OTH, ["GREEN TRENDS"]),
}
CAT_WEIGHT = {FOOD: 22, GRO: 14, TRN: 12, SHP: 14, BIL: 10, ENT: 8, HLT: 6, TRV: 6, OTH: 3}
GENERIC = ["SHARMA GENERAL STORE", "GUPTA TRADERS", "SUNRISE ENTERPRISES", "LAXMI STORES", "OM SAI TRDRS",
           "NEW BOMBAY STORES", "BALAJI ENTERPRISES", "SHREE KRISHNA TRDRS", "STAR MART", "MODERN STORES",
           "ROYAL ENTERPRISES", "GANESH TRADERS", "NEW STAR TRDRS", "PRAKASH STORES"]
PERSONS = ["Rohan G", "Dev M", "Nisha B", "Kavya N", "Vikram L", "Anita D", "Karan J", "Pooja R", "Aman S",
           "Divya M", "Neha K", "Sameer P", "Riya T", "Harsh V", "Isha C", "Manish A", "Tanvi B", "Yash O",
           "Aditi F", "Naveen H"]
EMPLOYERS = ["Fern Analytics", "Harbor Labs", "Pine Systems", "Coral Retail", "Quartz Infotech", "Sage Consulting",
             "Delta Foods"]
RAILS = ["Amazon Pay", "Google Pay", "PhonePe", "Paytm"]
WALLETS = ["Paytm Wallet", "Lotus Pay Wallet", "PhonePe Wallet", "Amazon Pay Balance"]
FEE_TEXT = ["SMS alert charges", "debit card annual fee", "minimum balance penalty", "account maintenance charges"]

# --- leakage controls -----------------------------------------------------
RESERVED_FORMATS = ["teak", "willow", "juniper", "aspen"]
HELD_OUT = ["cleartrip", "inox", "reliance fresh", "dr mehta", "kirana", "wellness forever", "mahanagar",
            "tata power", "cafe coffee day", "xyz trdrs", "chai sutta", "orchid tech", "birch software",
            "arjun p", "sana r", "meera k", "ishaan t", "tara s", "rahul"]


def indian_group(n):
    s = str(n)
    if len(s) <= 3: return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
    if head: parts.insert(0, head)
    return ",".join(parts) + "," + tail


def fmt_amt(rng, a, dec=True):
    whole, frac = f"{a:.2f}".split(".")
    w = int(whole)
    g = indian_group(w) if (w >= 100000 and rng.random() < 0.7) else f"{w:,}"
    return f"{g}.{frac}" if (dec or frac != "00") else g


def rand_amt(rng, lo, hi):
    a = math.exp(rng.uniform(math.log(lo), math.log(hi)))
    a = round(a) if rng.random() < 0.6 else round(a, 2)
    return float(a) if a > 0 else float(lo)


RANGE = {FOOD: (60, 1800), GRO: (40, 3500), TRN: (20, 2500), SHP: (199, 12000), BIL: (99, 6000),
         ENT: (99, 1500), HLT: (80, 5000), TRV: (800, 25000), OTH: (50, 5000), XFR: (50, 10000)}


def d1(d): return d.strftime("%d-%m-%y")
def d2(d): return d.strftime("%d-%b-%y")
def d3(d): return d.strftime("%d/%m/%y")
def d4(d): return d.strftime("%d-%m-%Y")
def d5(d): return d.strftime("%d%b%y")


def rdate(rng): return date(2026, 7, 1) + timedelta(days=rng.randint(0, 113))
def n(rng, k): return "".join(str(rng.randint(0, 9)) for _ in range(k))


def clock(rng):
    h, m = rng.randint(1, 12), rng.randint(0, 59)
    return f"{h:02d}:{m:02d}{rng.choice(['AM', 'PM'])}"


def noisy(rng, base):
    r = rng.random()
    if r < .25: return base
    if r < .55: return rng.choice([f"UPI/{n(rng,4)}/{base}", f"UPI-{base}", f"UPI/DR/{n(rng,6)}/{base}",
                                   f"UPI-{base}-{base.lower().replace(' ','')[:12]}@lotus-Ref {n(rng,4)}"])
    if r < .70: return base + rng.choice([" PVT LTD", " LTD BLR", " LTD", " INDIA PVT LTD", " MUMBAI", " BLR"])
    if r < .80: return f"{base} {rng.randint(10, 9999)}"
    if r < .88: return f"{base}*ORD {n(rng,4)}"
    if r < .95: return f"POS {n(rng,4)} {base}"
    return f"UPI/{n(rng,4)}/{base} {rng.randint(10,999)}"


def pick_merchant(rng):
    if rng.random() < 0.06:
        base = rng.choice(GENERIC)
        return base.title(), OTH, base
    cat = rng.choices(list(CAT_WEIGHT), weights=list(CAT_WEIGHT.values()))[0]
    cands = [(c, v) for c, v in CATALOG.items() if v[0] == cat]
    canon, (_, raws) = rng.choice(cands)
    return canon, cat, rng.choice(raws)


def L(m, a, dr, dt, cat, cur="INR"):
    return {"is_transaction": True, "merchant": m, "amount": float(a), "currency": cur, "direction": dr,
            "date": dt.isoformat() if dt else None, "category": cat}


NOT = {"is_transaction": False}
BANKS = ["Maple Bank", "Banyan Bank", "Lotus Pay", "Cedar Card"]


def ON(rng, d, fmt, p=0.07):
    """' on <date>' text, or nothing (label date then null)."""
    return (f" on {fmt(d)}", d) if rng.random() > p else ("", None)

# ---------------- transaction builders (each returns message, label) ----------------

def maple_debit(rng):
    canon, cat, base = pick_merchant(rng); a = rand_amt(rng, *RANGE[cat]); d = rdate(rng)
    raw = noisy(rng, base); on, dt = ON(rng, d, d1); bal = fmt_amt(rng, rand_amt(rng, 200, 90000))
    am = fmt_amt(rng, a, rng.random() < .8); ac = n(rng, 4)
    t = rng.choice([f"Maple Bank: Rs {am} debited from A/c XX{ac}{on} at {raw}. Avl bal Rs {bal}",
                    f"Maple Bank: Rs {am} debited from A/c XX{ac}{on} at {raw}. Avl bal Rs {bal}. Not you? Call 1800-000-111",
                    f"Dear customer, Rs {am} debited from your Maple Bank A/c XX{ac}{on} at {raw}. Avl bal Rs {bal}"])
    if rng.random() < .06: t = t.lower()
    return t, L(canon, a, "debit", dt, cat)


def maple_person_debit(rng):
    p = rng.choice(PERSONS); a = rand_amt(rng, *RANGE[XFR]); d = rdate(rng); on, dt = ON(rng, d, d1)
    return (f"Maple Bank: Rs {fmt_amt(rng,a)} debited from A/c XX{n(rng,4)}{on} at UPI/DR/{n(rng,6)}/{p.upper()}. "
            f"Avl bal Rs {fmt_amt(rng, rand_amt(rng,200,50000))}"), L(p, a, "debit", dt, XFR)


def maple_credit_person(rng):
    p = rng.choice(PERSONS); a = rand_amt(rng, *RANGE[XFR]); d = rdate(rng); on, dt = ON(rng, d, d1)
    return (f"Maple Bank: Rs {fmt_amt(rng,a)} credited to A/c XX{n(rng,4)}{on}. Info: UPI/CR/{n(rng,4)}/{p.upper()}. "
            f"Avl bal Rs {fmt_amt(rng, rand_amt(rng,500,90000))}"), L(p, a, "credit", dt, XFR)


def maple_refund(rng):
    canon, cat, base = pick_merchant(rng)
    while cat in (OTH, BIL): canon, cat, base = pick_merchant(rng)
    a = rand_amt(rng, *RANGE[cat]); d = rdate(rng); on, dt = ON(rng, d, d1)
    return (f"Maple Bank: Rs {fmt_amt(rng,a)} credited to A/c XX{n(rng,4)}{on}. Info: REFUND {base}. "
            f"Avl bal Rs {fmt_amt(rng, rand_amt(rng,500,90000))}"), L(canon, a, "credit", dt, INC)


def maple_salary(rng):
    e = rng.choice(EMPLOYERS); a = rand_amt(rng, 15000, 180000); d = rdate(rng); on, dt = ON(rng, d, d1, .03)
    return (f"Maple Bank: Rs {fmt_amt(rng,a)} credited to A/c XX{n(rng,4)}{on}. Info: SALARY {e.upper()}. "
            f"Avl bal Rs {fmt_amt(rng, rand_amt(rng,20000,300000))}"), L(e, a, "credit", dt, INC)


def maple_atm(rng):
    a = float(rng.choice([500, 1000, 2000, 3000, 4000, 5000, 10000])); d = rdate(rng); on, dt = ON(rng, d, d1)
    t = rng.choice([f"Maple Bank: Rs {fmt_amt(rng,a)} withdrawn from A/c XX{n(rng,4)} at ATM{on}. Avl bal Rs {fmt_amt(rng, rand_amt(rng,200,50000))}",
                    f"Maple Bank: Rs {fmt_amt(rng,a,False)} withdrawn at ATM from A/c XX{n(rng,4)}{on}. Avl bal Rs {fmt_amt(rng, rand_amt(rng,200,50000))}"])
    return t, L("ATM", a, "debit", dt, XFR)


def maple_fee(rng):
    a = rand_amt(rng, 10, 900); d = rdate(rng); on, dt = ON(rng, d, d1)
    return (f"Maple Bank: Rs {fmt_amt(rng,a)} debited from A/c XX{n(rng,4)}{on} towards {rng.choice(FEE_TEXT)}. "
            f"Avl bal Rs {fmt_amt(rng, rand_amt(rng,200,50000))}"), L("Maple Bank", a, "debit", dt, BIL)


def maple_self(rng):
    a = rand_amt(rng, 500, 40000); d = rdate(rng); on, dt = ON(rng, d, d1)
    t = rng.choice([f"Maple Bank: Rs {fmt_amt(rng,a)} debited from A/c XX{n(rng,4)}{on} as self transfer to your own A/c XX{n(rng,4)}. Avl bal Rs {fmt_amt(rng, rand_amt(rng,200,50000))}",
                    f"Maple Bank: Rs {fmt_amt(rng,a)} debited from A/c XX{n(rng,4)}{on}, transfer to own A/c XX{n(rng,4)} (Self). Avl bal Rs {fmt_amt(rng, rand_amt(rng,200,50000))}"])
    return t, L("Self Transfer", a, "debit", dt, XFR)


def maple_nomerchant(rng):
    a = rand_amt(rng, 20, 2500); d = rdate(rng); on, dt = ON(rng, d, d1, .04)
    return (f"Maple Bank: Rs {fmt_amt(rng,a,False)} debited from A/c XX{n(rng,4)}{on} via UPI. "
            f"Avl bal Rs {fmt_amt(rng, rand_amt(rng,200,50000))}"), L("Maple Bank", a, "debit", dt, OTH)


def banyan_debit(rng):
    canon, cat, base = pick_merchant(rng); d = rdate(rng); card = n(rng, 4)
    foreign = cat in (ENT, SHP) and canon in ("Netflix", "Spotify", "Steam", "Airbnb") and rng.random() < .3
    if foreign:
        a = round(rng.uniform(4, 40), 2); cur = "USD"; am = f"{a:.2f}"
    else:
        a = rand_amt(rng, *RANGE[cat]); cur = "INR"; am = fmt_amt(rng, a)
    on, dt = ON(rng, d, d2, .05); tm = f" {clock(rng)}" if dt else ""
    tail = rng.choice([f" Avl lmt INR {fmt_amt(rng, rand_amt(rng,2000,90000))}.", ".", " Not you? Call 1800-000-111"])
    return (f"BANYAN BANK: {cur} {am} spent on card ending {card} at {noisy(rng, base)}{on}{tm}{tail}"), \
        L(canon, a, "debit", dt, cat, cur)


def banyan_refund(rng):
    canon, cat, base = pick_merchant(rng)
    while cat in (OTH, BIL): canon, cat, base = pick_merchant(rng)
    a = rand_amt(rng, *RANGE[cat]); d = rdate(rng); on, dt = ON(rng, d, d2, .03)
    return f"BANYAN BANK: INR {fmt_amt(rng,a)} credited to card ending {n(rng,4)}{on}. Refund from {base}.", \
        L(canon, a, "credit", dt, INC)


def banyan_emi(rng):
    a = rand_amt(rng, 1200, 25000); d = rdate(rng)
    return f"BANYAN BANK: INR {fmt_amt(rng,a)} auto-debited on {d2(d)} towards EMI loan A/c {n(rng,4)}. Thank you.", \
        L("Banyan Bank", a, "debit", d, BIL)


def lotus_person(rng):
    p = rng.choice(PERSONS); a = rand_amt(rng, *RANGE[XFR]); d = rdate(rng); on, dt = ON(rng, d, d3, .08)
    if rng.random() < .65:
        return f"Rs {fmt_amt(rng,a,False)} sent to {p} via Lotus Pay UPI{on}. UPI Ref {n(rng,10)}.", L(p, a, "debit", dt, XFR)
    return f"Rs {fmt_amt(rng,a,False)} received from {p} via Lotus Pay UPI{on}. UPI Ref {n(rng,10)}.", L(p, a, "credit", dt, XFR)


def lotus_merchant(rng):
    canon, cat, base = pick_merchant(rng); a = rand_amt(rng, *RANGE[cat]); d = rdate(rng); on, dt = ON(rng, d, d3, .08)
    tail = rng.choice([" If not you, report in app.", ""])
    return f"Rs {fmt_amt(rng,a,False)} sent to {base} via Lotus Pay UPI{on}. UPI Ref {n(rng,10)}.{tail}", \
        L(canon, a, "debit", dt, cat)


def lotus_wallet(rng):
    w = rng.choice(WALLETS); a = float(rng.choice([100, 200, 500, 1000, 2000, 5000])); d = rdate(rng); on, dt = ON(rng, d, d3)
    return f"Rs {fmt_amt(rng,a,False)} added to {w}{' via UPI' if rng.random()<.5 else ''}{on}. Ref {n(rng,8)}", \
        L(w, a, "debit", dt, XFR)


def cedar_debit(rng):
    canon, cat, base = pick_merchant(rng); a = rand_amt(rng, *RANGE[cat]); d = rdate(rng); on, dt = ON(rng, d, d4, .05)
    return f"Rs.{fmt_amt(rng,a)} Dr. to Cedar Card {n(rng,4)} at {noisy(rng, base)}{on}. Pls check your statement.", \
        L(canon, a, "debit", dt, cat)


def cedar_refund(rng):
    canon, cat, base = pick_merchant(rng)
    while cat in (OTH, BIL): canon, cat, base = pick_merchant(rng)
    a = rand_amt(rng, *RANGE[cat]); d = rdate(rng); on, dt = ON(rng, d, d4, .03)
    return f"Rs.{fmt_amt(rng,a)} Cr. to Cedar Card {n(rng,4)}{on}. Refund from {base}.", L(canon, a, "credit", dt, INC)


def cedar_fee(rng):
    a = rand_amt(rng, 100, 2500); d = rdate(rng)
    return f"Rs.{fmt_amt(rng,a)} Dr. to Cedar Card {n(rng,4)} towards {rng.choice(['annual fee','late payment charges','GST on charges'])} on {d4(d)}.", \
        L("Cedar Card", a, "debit", d, BIL)


def rail_payee(rng):
    canon, cat, base = pick_merchant(rng); a = rand_amt(rng, *RANGE[cat]); d = rdate(rng); app = rng.choice(RAILS)
    return f"Paid Rs {fmt_amt(rng,a,False)} via {app} to {base} on {d5(d)} Ref {n(rng,8)}", L(canon, a, "debit", d, cat)


def rail_only(rng):
    a = rand_amt(rng, 50, 3000); d = rdate(rng); app = rng.choice(RAILS)
    t = rng.choice([f"Paid Rs {fmt_amt(rng,a,False)} via {app} on {d5(d)} Ref {n(rng,5)}",
                    f"You paid Rs {fmt_amt(rng,a,False)} using {app} on {d5(d)}. Txn ID {n(rng,5)}"])
    return t, L(app, a, "debit", d, OTH)


def hinglish(rng):
    kind = rng.choice(["debit", "debit2", "credit", "kat", "bheje", "atm", "kharch", "mil"])
    d = rdate(rng); a = rand_amt(rng, 30, 3000)
    if kind in ("debit", "debit2", "kat", "kharch"):
        canon, cat, base = pick_merchant(rng); a = rand_amt(rng, *RANGE[cat])
    if kind == "debit":
        return f"Aapke A/c XX{n(rng,4)} se Rs {fmt_amt(rng,a)} debit hue hain {d1(d)} ko, {base}. Bal Rs {fmt_amt(rng, rand_amt(rng,200,50000))}", L(canon, a, "debit", d, cat)
    if kind == "debit2":
        return f"Rs {fmt_amt(rng,a,False)} aapke account se kat gaye {base} par, {d1(d)}. A/c XX{n(rng,4)}", L(canon, a, "debit", d, cat)
    if kind == "kat":
        return f"Rs {fmt_amt(rng,a,False)} kat gaye {base} ke liye, Lotus Pay UPI, {d3(d)}", L(canon, a, "debit", d, cat)
    if kind == "kharch":
        return f"Rs {fmt_amt(rng,a,False)} {base} par kharch hue, Banyan card {n(rng,4)}, {d2(d)}", L(canon, a, "debit", d, cat)
    p = rng.choice(PERSONS); a = rand_amt(rng, *RANGE[XFR])
    if kind == "credit":
        return f"Rs {fmt_amt(rng,a,False)} aapke account me credit hue hain {p} se UPI ke through. {d1(d)}", L(p, a, "credit", d, XFR)
    if kind == "mil":
        return f"Rs {fmt_amt(rng,a,False)} {p} se mil gaye, Lotus Pay UPI, {d3(d)}", L(p, a, "credit", d, XFR)
    if kind == "bheje":
        return f"Aapne {p} ko Rs {fmt_amt(rng,a,False)} bheje Lotus Pay UPI se. Date {d3(d)}", L(p, a, "debit", d, XFR)
    a = float(rng.choice([1000, 2000, 3000, 4000, 5000]))
    return f"Rs {fmt_amt(rng,a,False)} ATM se cash nikala {d1(d)}. A/c XX{n(rng,4)}", L("ATM", a, "debit", d, XFR)

# ---------------- non-transaction builders ----------------

def nt(rng):
    bank = rng.choice(BANKS); Bank = bank.upper() if rng.random() < .4 else bank
    a = fmt_amt(rng, rand_amt(rng, 100, 5000), False); d = rdate(rng); ac = n(rng, 4); card = n(rng, 4)
    otp = n(rng, 6); p = rng.choice(PERSONS); _, _, base = pick_merchant(rng); M = base.title()
    kind = rng.choices(["otp", "promo", "bal", "fail", "req", "due", "login", "block", "kyc", "stmt", "rev"],
                       weights=[16, 14, 12, 10, 8, 8, 7, 5, 4, 5, 11])[0]
    T = {
        "otp": [f"{Bank}: {otp} is your OTP for NetBanking. Valid {rng.randint(3,10)} min. Do not share.",
                f"Dear customer, your OTP for txn of Rs {a} at {base} is {otp}. Valid 10 mins. Do not share. -{Bank}",
                f"{otp} is your {bank} verification code. Do not share it with anyone.",
                f"Aapka OTP {otp} hai. Kisi ko mat batayein. -{bank}",
                f"{Bank}: Use {otp} as OTP for your transaction of Rs {a}. Never share."],
        "promo": [f"Get flat {rng.choice([5,10,15,20])}% cashback on your next {rng.randint(2,5)} {bank} UPI payments! T&C apply.",
                  f"{Bank}: Pre-approved personal loan up to INR {rng.choice(['2,00,000','5,00,000','10,00,000'])} for you! Apply now.",
                  f"Festive sale! Shop on {M} and get up to {rng.choice([40,50,60])}% off. Use your {bank} card for extra {rng.choice([5,10])}% off.",
                  f"Offer! Pehle order par {rng.choice([30,50])}% off, code NEW{rng.randint(10,99)}. Abhi {M} kholein.",
                  f"Win up to Rs {a} cashback on your next payment with {bank}. T&C apply."],
        "bal": [f"{Bank}: Your A/c XX{ac} available balance is Rs {fmt_amt(rng, rand_amt(rng,100,90000))} as on {d1(d)}.",
                f"{Bank}: Avl limit on card ending {card} is INR {fmt_amt(rng, rand_amt(rng,1000,90000))}.",
                f"{bank} wallet balance: Rs {fmt_amt(rng, rand_amt(rng,10,5000))}."],
        "fail": [f"{Bank}: Your payment of Rs {a} to {base} has failed. No amount has been debited.",
                 f"{bank}: Transaction of Rs {a} could not be completed. Please retry. No money deducted.",
                 f"Payment of Rs {a} to {M} failed. Nothing was debited from your account."],
        "req": [f"{p} has requested Rs {a} on Lotus Pay UPI. Open app to pay or decline.",
                f"{p} is requesting Rs {a} from you. Approve in your UPI app.",
                f"Collect request: {p} wants Rs {a}. Approve or decline in the app."],
        "due": [f"Your electricity bill of Rs {a} is due on {d1(d)}. Pay on time to avoid late fee.",
                f"Cedar Card: Minimum due Rs {a} on card ending {card} is payable by {d1(d)}.",
                f"Aapke {rng.choice(['bijli','gas','phone'])} bill ka Rs {a} due hai {d1(d)} tak. Jaldi bhugtan karein.",
                f"{Bank}: Your card ending {card} has a payment of Rs {a} due by {d1(d)}. Pay now to avoid charges."],
        "login": [f"{Bank}: New login to NetBanking from {rng.choice(['Chrome','Safari','Firefox'])}, {rng.choice(['Delhi','Pune','Chennai','Kolkata'])} on {d1(d)} at {clock(rng)}. Not you? Call 1800-000-111",
                  f"{Bank}: Login to mobile app from a new device on {d1(d)}. Not you? Call 1800-000-111"],
        "block": [f"{Bank}: Your card ending {card} has been temporarily blocked as per your request.",
                  f"{Bank}: Your card ending {card} has been unblocked. You can use it again."],
        "kyc": [f"Dear customer, your KYC is due for renewal. Update before {d1(d)} to avoid restrictions. -{bank}"],
        "stmt": [f"Your {bank} statement for {d.strftime('%b')}-26 is ready. View in the app.",
                 f"{Bank}: e-statement for A/c XX{ac} is ready. Download from NetBanking."],
        "rev": [f"{Bank}: Payment of Rs {a} to {base} failed. Debited amount will be reversed in {rng.choice(['3-5','5-7','2-3'])} days. Ref {n(rng,5)}",
                f"{Bank}: Your transaction of Rs {a} at {base} failed. If money was debited, it will be reversed in {rng.choice(['3-5','5-7'])} working days."],
    }
    return rng.choice(T[kind]), NOT, kind

BUILDERS = [  # (function, family, weight)
    (maple_debit, "maple", 13), (maple_person_debit, "maple", 2), (maple_credit_person, "maple", 2),
    (maple_refund, "maple", 2), (maple_salary, "maple", 1.5), (maple_atm, "maple", 1.5),
    (maple_fee, "maple", 1.5), (maple_self, "maple", 1), (maple_nomerchant, "maple", 1),
    (banyan_debit, "banyan", 14), (banyan_refund, "banyan", 2), (banyan_emi, "banyan", 1.5),
    (lotus_person, "lotus", 7), (lotus_merchant, "lotus", 9), (lotus_wallet, "lotus", 1.5),
    (cedar_debit, "cedar", 11), (cedar_refund, "cedar", 1.5), (cedar_fee, "cedar", 1),
    (rail_payee, "rail", 5), (rail_only, "rail", 1.5), (hinglish, "hinglish", 7), (nt, "non_txn", 13),
]


def norm(t): return re.sub(r"\d", "#", t.lower())


def amount_in_text(msg, a):
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", msg)]
    return any(abs(x - a) < 0.005 for x in nums)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2400); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/seed_raw.jsonl"); ap.add_argument("--splits-out", default="data/splits.json")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    fixed = {}
    for path in ("data/gold_test.jsonl", "data/dev.jsonl"):
        for line in open(path, encoding="utf-8"):
            fixed[norm(json.loads(line)["message"])] = path
    funcs, weights = [b[0] for b in BUILDERS], [b[2] for b in BUILDERS]
    fam = {b[0]: b[1] for b in BUILDERS}
    seen, rows, dropped = set(fixed), [], Counter()
    tries = 0
    while len(rows) < a.n and tries < a.n * 40:
        tries += 1
        f = rng.choices(funcs, weights)[0]
        out = f(rng)
        msg, lab = out[0], out[1]
        kind = out[2] if len(out) > 2 else f.__name__
        k = norm(msg)
        if k in fixed: dropped["same shape as gold/dev"] += 1; continue
        if k in seen: dropped["duplicate seed"] += 1; continue
        low = msg.lower()
        if any(x in low for x in RESERVED_FORMATS): dropped["reserved gold-only format"] += 1; continue
        if any(x in low for x in HELD_OUT) or any(x in (lab.get("merchant") or "").lower() for x in HELD_OUT):
            dropped["held-out merchant/person"] += 1; continue
        if lab["is_transaction"] and not amount_in_text(msg, lab["amount"]): dropped["amount not in text"] += 1; continue
        seen.add(k)
        rows.append({"id": f"s{len(rows)+1:04d}", "message": msg, "label": lab, "family": fam[f], "kind": kind})
    with open(a.out, "w", encoding="utf-8") as fh:
        for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = Counter(r["family"] for r in rows)
    nt_n = sum(1 for r in rows if not r["label"]["is_transaction"])
    print(f"wrote {a.out}: {len(rows)} seeds  (tries {tries})")
    print("by family:", dict(c)); print(f"non-transactions: {nt_n} ({nt_n/len(rows):.1%})")
    print("dropped:", dict(dropped))
    print("distinct merchants:", len({r['label']['merchant'] for r in rows if r['label']['is_transaction']}))
    splits = {
        "note": "Which formats, merchants, people and employers go in which set. Gold uses the unseen formats, which never appear in train or dev.",
        "formats": {"train_and_dev": ["Maple Bank (A/c style)", "Banyan Bank (card style)", "Lotus Pay UPI", "Cedar Card",
                                      "Amazon Pay / Google Pay / PhonePe / Paytm rails", "Hinglish phrasings"],
                    "gold_seen_slice": "same six training formats as above, different messages",
                    "gold_only_unseen": ["Teak Bank", "Willow Co-op", "Juniper Payments", "Aspen SFB"]},
        "held_out_from_training": {"merchants": ["Cleartrip", "Inox Movies", "Reliance Fresh", "Dr Mehta Clinic",
                                                 "Kirana Store", "Wellness Forever", "Mahanagar Gas", "Tata Power",
                                                 "Cafe Coffee Day", "Xyz Trdrs", "Chai Sutta Bar"],
                                   "people": ["Arjun P", "Sana R", "Meera K", "Ishaan T", "Tara S", "Rahul"],
                                   "employers": ["Orchid Tech", "Birch Software"]},
        "merchant_overlap_policy": "Common brands (Swiggy, Amazon, Uber...) appear in both train and gold. Only the unseen-format slice is leakage-controlled by format; the long-tail merchants above are held out entirely.",
        "dedupe_rule": "Lowercase, digits masked. A seed is dropped if its masked text matches any gold or dev message or another seed.",
        "seed_counts_by_family": dict(c), "seed_generator": {"file": "gen/templates.py", "seed": a.seed, "n": len(rows)},
    }
    json.dump(splits, open(a.splits_out, "w"), indent=2)
    print("wrote", a.splits_out)
    return rows


if __name__ == "__main__":
    rows = main()
    rng = random.Random(1)
    print("\n--- 24 random samples ---")
    for r in rng.sample(rows, 24):
        lab = r["label"]
        short = "NOT-TXN" if not lab["is_transaction"] else f"{lab['merchant']} | {lab['amount']} {lab['currency']} | {lab['direction']} | {lab['date']} | {lab['category']}"
        print(f"[{r['family']}] {r['message']}\n     -> {short}")