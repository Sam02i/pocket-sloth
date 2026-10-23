# Pocket Sloth Labeling Guide

This guide decides what the "right answer" is for every alert message. It was written **before** any gold-set labeling began. Gold labels follow this guide exactly; if a case is not covered, add a rule here first, then label.

Everything here uses synthetic or anonymized messages only. No real account numbers, card numbers, or personal names.

## Output schema

One JSON object per message:

```json
{
  "is_transaction": true,
  "merchant": "Swiggy",
  "amount": 349.00,
  "currency": "INR",
  "direction": "debit",
  "date": "2026-10-14",
  "category": "Food & Delivery"
}
```

If the message is not a transaction, the output is exactly `{"is_transaction": false}` with no other fields.

## 1. Fields

| Field | Rule |
|---|---|
| `is_transaction` | `true` only if money actually moved (debited, credited, refunded, or reversed). See section 5. |
| `amount` | The amount of *this* transaction, as a plain number: no commas, no ₹ or Rs. `1,249.50` becomes `1249.50`. Never use the "available balance" figure. |
| `currency` | `"INR"` unless the message clearly says otherwise (for example USD for a foreign card spend). |
| `direction` | `"debit"` when money leaves you, `"credit"` when money comes in. A refund is a `credit`. |
| `date` | `YYYY-MM-DD`. Two-digit years like `14-10-26` mean 2026. **If the message has no date, use `null`.** Never guess a date. |
| `merchant` | See section 2. |
| `category` | See section 3. |

## 2. Merchant names

The `merchant` field holds the clean, everyday name a person would say out loud.

1. **Remove the noise.** Delete reference numbers, order IDs, asterisks, branch codes, and legal endings like PVT LTD, LTD, PAYMENTS.
2. **Use the brand name in Title Case.** Expand short codes to the brand people know (`AMZN` becomes Amazon).
3. **Never invent a brand.** If a messy string can't be identified, clean it lightly and keep it (`XYZ TRDRS 22` becomes `Xyz Trdrs`). If the message shows no merchant at all, use the bank name shown (for example `Maple Bank`) and the category **Other**.
4. **Payments to people.** Keep the name as written in the message, in Title Case (made-up names only).
5. **One spelling per merchant.** The merchant dictionary in `gen/templates.py` is the single source of spellings.

### Sub-brands

If the message shows a sub-brand, it becomes its own merchant with its own category. If the message shows only the parent brand, use the parent's main category. We only split a brand when its sub-brands would land in different categories.

| Message says | `merchant` | `category` |
|---|---|---|
| `SWIGGY*ORD 8812` | Swiggy | Food & Delivery |
| `SWIGGY INSTAMART` | Swiggy Instamart | Groceries |
| `ZOMATO LTD BLR` | Zomato | Food & Delivery |
| `BLINKIT` | Blinkit | Groceries |
| `DINEOUT` | Dineout | Food & Delivery |
| `AMZN PAY INDIA` | Amazon | Shopping |
| `XYZ TRDRS 22` | Xyz Trdrs | Other |
| `UPI-RAHUL S-...` (made-up name) | Rahul S | Transfers |

### Payment apps are "rails", not merchants

Amazon Pay, Google Pay, PhonePe, Paytm, BHIM, and bank UPI are ways of paying. Category follows the **destination**, not the tool.

1. If the message names who was paid, use that name and its category.
2. If it names only the payment app, use the app as the merchant and the category **Other**.
3. Wallet top-ups go to **Transfers**.

| Message says | `merchant` | `category` |
|---|---|---|
| `Paid to BSES via Amazon Pay` | BSES | Bills & Utilities |
| `Paid to Swiggy via PhonePe` | Swiggy | Food & Delivery |
| `Paid Rs 500 via Amazon Pay` (no payee shown) | Amazon Pay | Other |
| `Paid to Amazon Pay` (clearly a shop purchase on Amazon) | Amazon | Shopping |

If it is unclear whether an Amazon Pay message is a purchase or a wallet top-up, use Other.

## 3. Categories (fixed list of 11)

| Category | What goes in it |
|---|---|
| Food & Delivery | Restaurants, cafes, Swiggy, Zomato, Dineout, takeaway |
| Groceries | Supermarkets, Blinkit, Zepto, BigBasket, Swiggy Instamart, vegetable shops |
| Transport | Uber, Ola, Rapido, metro, fuel, FASTag, parking |
| Shopping | Clothes, electronics, Amazon, Flipkart, Myntra, general retail |
| Bills & Utilities | Electricity, phone and internet recharge, rent, insurance, EMI, bank and card fees |
| Entertainment | Netflix, Spotify, movies, games, events |
| Health | Pharmacy, doctor, hospital, gym, lab tests |
| Travel | Flights, trains, hotels, holiday bookings |
| Transfers | Person-to-person payments, ATM withdrawals, self-transfers, wallet top-ups |
| Income & Refunds | Salary, interest, cashback, refunds, reversals, money received from businesses |
| Other | Anything you honestly cannot place |

### Tiebreak rules

1. **Category follows what the merchant mainly is, not what was bought.** Amazon is always Shopping, because the message never says what was in the cart.
2. **Credits go to Income & Refunds**, except person-to-person money received and self-transfer credits, which go to **Transfers**.
3. **When the message gives no clue, use Other.** Never guess a category from a vague merchant name.
4. **Transport vs Travel.** Transport is for everyday trips. Travel is for booked trips (flights, trains, hotels).
5. **Generic shop names** (for example `KIRANA STORE 12`) go to **Other**, because the name could be any kind of shop.

## 4. Special cases

1. **Refunds.** `direction: "credit"`, `category: "Income & Refunds"`, `merchant` is the shop that refunded. A refund is its own row. It is **not** matched to the original purchase in the labels (the model sees one message at a time). Optional matching happens later in `ledger.py`.
2. **Reversals.** If the message is only about money being returned, it is a credit, Income & Refunds, with the merchant if named.
3. **ATM withdrawals.** `debit`, `merchant: "ATM"`, `category: "Transfers"`. Do not keep the bank or location.
4. **Self-transfers.** If the message clearly says it is your own account or wallet: `debit` on the sending side, `credit` on the receiving side, `merchant: "Self Transfer"`, `category: "Transfers"`. If it is not clear, treat it as a person-to-person payment.
5. **Fees and charges** (SMS charges, annual card fee, penalty). `debit`, `Bills & Utilities`, `merchant` is the bank or card name if shown, otherwise `null`.
6. **Interest and cashback received.** `credit`, `Income & Refunds`.
7. **Standing instructions and EMIs.** Real debits, so they count. EMIs go to `Bills & Utilities`. The merchant is the lender or bank if the message names one, and `null` if no lender is named.
8. **Salary and other credits from a business.** `credit`, `Income & Refunds`, and the merchant is the employer or sender name as shown (for example `Orchid Tech`).
9. **Foreign currency.** Use the currency code the message shows (for example `USD`) and copy the amount as shown (`12.99`). The category follows the merchant as usual.

## 5. What counts as not-a-transaction

The test: **did money actually move?** If not, output `{"is_transaction": false}`.

**Always `false`:**

1. OTPs and verification codes.
2. Promos and offers ("Get 10% cashback on your next order!").
3. Balance-only alerts.
4. Failed payments where nothing was debited ("Payment of Rs 300 failed. No amount debited.").
5. Payment requests ("Rahul has requested Rs 500 from you"). A request is not a payment until approved.
6. Reminders and bills due ("Your electricity bill of Rs 1,200 is due on 28th"). Nothing has been paid yet.
7. Login alerts, card block or unblock notices, KYC reminders, statement-ready notices.
8. **Failed payment with a pending reversal** ("Payment of Rs 300 failed, amount debited will be reversed in 3-5 days"). The message is a notice, not a completed transaction. The reversal credit alert that arrives later is its own `true` row.

**Always `true`:** a debit or credit alert that also carries extra text, such as a promo line at the end. The money moved, so it is a transaction. Ignore the promo.

## 6. Reporting

Category accuracy is reported **separately** from the objective fields (amount, date, direction, is_transaction), because category labels are subjective. This guide is what makes the category numbers defensible.