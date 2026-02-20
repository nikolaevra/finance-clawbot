#!/usr/bin/env python3
"""
One-shot script to seed mock QBO integration + accounts + transactions
into Supabase.  Run once, then delete.

Usage:
    cd backend
    source venv/bin/activate
    python seed_mock_accounting.py
"""
import os, uuid, random
from datetime import datetime, timedelta, timezone, date
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sb = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)

# ── Resolve user_id (pick the first user) ─────────────────────
users = sb.auth.admin.list_users()
if not users:
    print("No users found in auth.users — sign up first.")
    raise SystemExit(1)

user_id = users[0].id
print(f"Seeding data for user {user_id}")

# ── 1.  Create integration ────────────────────────────────────
now = datetime.now(timezone.utc)
integration_id = str(uuid.uuid4())

sb.table("integrations").insert({
    "id": integration_id,
    "user_id": user_id,
    "provider": "quickbooks",
    "integration_name": "QuickBooks Online",
    "account_token": "mock-token-not-real",
    "status": "active",
    "last_sync_at": now.isoformat(),
    "last_sync_status": "Synced 18 accounts, 45 transactions",
    "merge_account_id": "mock-merge-account-id",
}).execute()
print(f"Created integration {integration_id}")

# ── 2.  Chart of accounts ─────────────────────────────────────
ACCOUNTS = [
    # (name, classification, type, balance)
    ("Business Checking",       "asset",     "bank",                   42_350.67),
    ("Savings Account",         "asset",     "bank",                   125_000.00),
    ("Accounts Receivable",     "asset",     "accounts_receivable",    18_750.00),
    ("Undeposited Funds",       "asset",     "other_current_asset",    3_200.00),
    ("Inventory Asset",         "asset",     "other_current_asset",    8_450.00),
    ("Prepaid Expenses",        "asset",     "other_current_asset",    2_100.00),
    ("Accounts Payable",        "liability", "accounts_payable",       -9_875.50),
    ("Credit Card - Amex",      "liability", "credit_card",            -4_320.12),
    ("Credit Card - Visa",      "liability", "credit_card",            -1_780.00),
    ("Loan Payable",            "liability", "long_term_liability",    -45_000.00),
    ("Owner's Equity",          "equity",    "owners_equity",          -100_000.00),
    ("Retained Earnings",       "equity",    "retained_earnings",      -28_500.00),
    ("Sales Revenue",           "revenue",   "income",                 -187_400.00),
    ("Service Revenue",         "revenue",   "income",                 -42_600.00),
    ("Interest Income",         "revenue",   "other_income",           -1_250.00),
    ("Rent Expense",            "expense",   "expense",                24_000.00),
    ("Payroll Expense",         "expense",   "expense",                72_500.00),
    ("Office Supplies",         "expense",   "expense",                3_475.25),
]

account_ids = {}
for name, classification, acct_type, balance in ACCOUNTS:
    rid = str(uuid.uuid4())
    account_ids[name] = rid
    sb.table("accounting_accounts").insert({
        "user_id": user_id,
        "integration_id": integration_id,
        "remote_id": rid,
        "name": name,
        "description": f"{name} — imported from QuickBooks Online",
        "classification": classification,
        "type": acct_type,
        "status": "active",
        "current_balance": balance,
        "currency": "USD",
        "remote_created_at": (now - timedelta(days=365)).isoformat(),
        "remote_updated_at": now.isoformat(),
    }).execute()

print(f"Created {len(ACCOUNTS)} accounts")

# ── 3.  Transactions ──────────────────────────────────────────

VENDORS = [
    "Amazon Business", "Staples", "WeWork", "Google Cloud",
    "Adobe Systems", "FedEx", "AT&T", "Comcast Business",
    "Delta Airlines", "Uber", "Home Depot", "Costco Wholesale",
    "Gusto Payroll", "ADP", "Blue Cross Blue Shield",
]

CUSTOMERS = [
    "Acme Corp", "Globex Inc", "Initech LLC", "Umbrella Corp",
    "Stark Industries", "Wayne Enterprises", "Cyberdyne Systems",
]

EXPENSE_ACCOUNTS = ["Rent Expense", "Payroll Expense", "Office Supplies",
                    "Credit Card - Amex", "Credit Card - Visa"]
REVENUE_ACCOUNTS = ["Sales Revenue", "Service Revenue"]
BANK_ACCOUNTS = ["Business Checking", "Savings Account"]

EXPENSE_MEMOS = [
    "Monthly office rent", "Bi-weekly payroll", "Office supplies order",
    "Cloud hosting fees", "Software subscription", "Shipping costs",
    "Internet service", "Phone bill", "Business travel", "Ride to client",
    "Maintenance supplies", "Bulk supplies purchase", "Team lunch",
    "Conference registration", "Marketing materials", "Insurance premium",
    "Legal consultation", "Accounting services", "Equipment repair",
    "Printer toner and paper",
]

INCOME_MEMOS = [
    "Invoice payment received", "Consulting engagement",
    "Monthly retainer", "Project milestone payment",
    "Annual subscription renewal", "Implementation fee",
    "Support contract", "Training session", "Advisory services",
]

transactions = []
start_date = date(2025, 7, 1)
end_date = date(2026, 2, 11)
day_count = (end_date - start_date).days

for i in range(45):
    rand_day = start_date + timedelta(days=random.randint(0, day_count))
    is_income = random.random() < 0.30  # ~30% income, 70% expense

    if is_income:
        amount = round(random.uniform(500, 15_000), 2)
        contact = random.choice(CUSTOMERS)
        acct_name = random.choice(REVENUE_ACCOUNTS)
        memo = random.choice(INCOME_MEMOS)
        txn_type = "income"
    else:
        amount = round(-random.uniform(15, 8_000), 2)
        contact = random.choice(VENDORS)
        acct_name = random.choice(EXPENSE_ACCOUNTS)
        memo = random.choice(EXPENSE_MEMOS)
        txn_type = "expense"

    rid = str(uuid.uuid4())
    deposit_acct = random.choice(BANK_ACCOUNTS)

    line_items = [
        {
            "account": acct_name,
            "amount": amount,
            "description": memo,
        },
        {
            "account": deposit_acct,
            "amount": -amount,
            "description": f"{'Deposit from' if is_income else 'Payment to'} {contact}",
        },
    ]

    transactions.append({
        "user_id": user_id,
        "integration_id": integration_id,
        "remote_id": rid,
        "transaction_date": rand_day.isoformat(),
        "number": f"{'INV' if is_income else 'EXP'}-{1000 + i}",
        "memo": memo,
        "total_amount": amount,
        "currency": "USD",
        "contact_name": contact,
        "account_name": acct_name,
        "account_remote_id": account_ids.get(acct_name, ""),
        "transaction_type": txn_type,
        "line_items": line_items,
        "remote_created_at": datetime.combine(rand_day, datetime.min.time(),
                                               tzinfo=timezone.utc).isoformat(),
        "remote_updated_at": now.isoformat(),
    })

# Sort by date for readability
transactions.sort(key=lambda t: t["transaction_date"])

for txn in transactions:
    sb.table("accounting_transactions").insert(txn).execute()

print(f"Created {len(transactions)} transactions")
print()
print("Done! Your QBO integration is active with mock data.")
print(f"  Integration ID: {integration_id}")
print(f"  Accounts:       {len(ACCOUNTS)}")
print(f"  Transactions:   {len(transactions)}")
