"""JM-ACCOUNTS SYSTEM - accounting engine (no GUI code in here)."""
import json, os, sys, datetime as dt

APP_NAME = "JM-ACCOUNTS SYSTEM"
from variant import DATA_FILE                   # each version keeps its own data file
TYPES = ["Asset", "Liability", "Equity", "Income", "Expense"]
SECTIONS = {
    "Asset": ["Current assets", "Non-current assets"],
    "Liability": ["Current liabilities", "Non-current liabilities"],
    "Equity": ["Equity"],
    "Income": ["Revenue", "Other income"],
    "Expense": ["Cost of sales", "Expenses"],
}
DEBIT_TYPES = ("Asset", "Expense")


def normal_side(t):
    return "Debit" if t in DEBIT_TYPES else "Credit"


def r2(x):
    return round(float(x) + 0.0, 2)


def fmt_date(iso):
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except Exception:
        return iso or ""


def parse_date(text):
    text = (text or "").strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(text, f).date()
        except ValueError:
            pass
    return None


def data_dir():
    forced = os.environ.get("JM_DATA_DIR")           # set by the Android app to its private storage
    if forced:
        os.makedirs(forced, exist_ok=True)
        return forced
    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    base = docs if os.path.isdir(docs) else home
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _code_key(c):
    c = str(c)
    return (0, int(c), c) if c.isdigit() else (1, 0, c.lower())


DEFAULT_SETTINGS = {
    "business": "", "period_end": "",
    "email_method": "Outlook", "smtp_host": "smtp.gmail.com", "smtp_port": 587,
    "smtp_user": "", "smtp_password": "", "smtp_from": "",
    "report_folder": "", "last_to": "",
}


class Books:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), DATA_FILE)
        self.settings = dict(DEFAULT_SETTINGS)
        self.accounts = []   # {code,name,type,section}
        self.entries = []    # {id,date,ref,lines:[{account,desc,dr,cr}]}
        self.items = []      # inventory: {id,code,name,kind,unit,cost,price,reorder}
        self.moves = []      # inventory: {id,date,item,type,qty,price,pay,party,note,journal_id}
        self.next_id = 1

    # ---------- persistence ----------
    def load(self):
        if not os.path.exists(self.path):
            old = os.path.join(os.path.dirname(self.path), "jm_data.json")       # first start of this version: begin from a COPY
            if DATA_FILE != "jm_data.json" and os.path.exists(old):                # of the existing books (the original is untouched)
                import shutil; shutil.copyfile(old, self.path)
                self._from_dict(json.load(open(self.path, encoding="utf-8"))); return
            seed = resource_path("seed.json")
            if os.path.exists(seed):
                self._from_dict(json.load(open(seed, encoding="utf-8")))
            self.save()
            return
        self._from_dict(json.load(open(self.path, encoding="utf-8")))

    def _from_dict(self, d):
        self.settings = dict(DEFAULT_SETTINGS); self.settings.update(d.get("settings", {}))
        self.accounts = d.get("accounts", [])
        self.entries = d.get("entries", [])
        self.items = d.get("items", []); self.moves = d.get("moves", [])
        self.next_id = max([e["id"] for e in self.entries] + [0]) + 1

    def to_dict(self):
        return {"settings": self.settings, "accounts": self.accounts, "entries": self.entries, "items": self.items, "moves": self.moves}

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ---------- chart of accounts ----------
    def sorted_accounts(self):
        return sorted(self.accounts, key=lambda a: _code_key(a["code"]))

    def account(self, name):
        for a in self.accounts:
            if a["name"] == name:
                return a
        return None

    def _check_account(self, code, name, typ, section, ignore=None):
        code, name = str(code).strip(), (name or "").strip()
        if not code: raise ValueError("Enter an account code.")
        if not name: raise ValueError("Enter an account name.")
        if typ not in TYPES: raise ValueError("Choose an account type.")
        if section not in SECTIONS[typ]:
            section = SECTIONS[typ][0]
        for a in self.accounts:
            if a is ignore: continue
            if a["code"] == code: raise ValueError(f"Code {code} is already used by '{a['name']}'.")
            if a["name"].lower() == name.lower(): raise ValueError(f"An account named '{a['name']}' already exists.")
        return code, name, typ, section

    def add_account(self, code, name, typ, section):
        code, name, typ, section = self._check_account(code, name, typ, section)
        self.accounts.append({"code": code, "name": name, "type": typ, "section": section})
        self.save()

    def update_account(self, old_name, code, name, typ, section):
        a = self.account(old_name)
        if not a: raise ValueError("Account not found.")
        code, name, typ, section = self._check_account(code, name, typ, section, ignore=a)
        if name != old_name:   # rename flows through every journal line
            for e in self.entries:
                for l in e["lines"]:
                    if l["account"] == old_name: l["account"] = name
        a.update(code=code, name=name, type=typ, section=section)
        self.save()

    def account_in_use(self, name):
        return any(l["account"] == name for e in self.entries for l in e["lines"])

    def delete_account(self, name):
        if self.account_in_use(name):
            raise ValueError(f"'{name}' has journal entries, so it cannot be deleted.\n"
                             "Delete or change those entries first.")
        self.accounts = [a for a in self.accounts if a["name"] != name]
        self.save()

    # ---------- journal ----------
    def next_ref(self):
        n = 0
        for e in self.entries:
            r = str(e.get("ref", ""))
            digits = "".join(ch for ch in r if ch.isdigit())
            if r[:1].upper() == "J" and digits:
                n = max(n, int(digits))
        return f"J{max(n, len(self.entries)) + 1}"

    def validate_entry(self, e, ignore_id=None):
        if not e.get("date"): raise ValueError("Pick a valid date.")
        ref = (e.get("ref") or "").strip()
        if not ref: raise ValueError("Enter a Ref.")
        for o in self.entries:
            if o["id"] != ignore_id and o["ref"].lower() == ref.lower():
                raise ValueError(f"Ref {ref} is already used by another journal entry.")
        lines = []
        for l in e["lines"]:
            dr, cr = r2(l.get("dr") or 0), r2(l.get("cr") or 0)
            if not l.get("account") and dr == 0 and cr == 0: continue
            if not self.account(l.get("account")): raise ValueError(f"'{l.get('account')}' is not in the chart of accounts.")
            if dr < 0 or cr < 0: raise ValueError("Amounts cannot be negative.")
            if dr and cr: raise ValueError("A line can have a debit or a credit, not both.")
            if not dr and not cr: raise ValueError(f"Enter an amount for {l['account']}.")
            lines.append({"account": l["account"], "desc": (l.get("desc") or "").strip(), "dr": dr, "cr": cr})
        if len(lines) < 2: raise ValueError("A journal entry needs at least two lines.")
        td, tc = r2(sum(l["dr"] for l in lines)), r2(sum(l["cr"] for l in lines))
        if td != tc: raise ValueError(f"Debits ({td:,.2f}) and credits ({tc:,.2f}) must be equal.")
        return {"date": e["date"], "ref": ref, "lines": lines}

    def add_entry(self, e):
        c = self.validate_entry(e); c["id"] = self.next_id; self.next_id += 1
        self.entries.append(c); self.save(); return c

    def update_entry(self, eid, e):
        c = self.validate_entry(e, ignore_id=eid); c["id"] = eid
        for i, o in enumerate(self.entries):
            if o["id"] == eid: self.entries[i] = c; break
        self.save()

    def delete_entry(self, eid):
        self.entries = [e for e in self.entries if e["id"] != eid]; self.save()

    def entry(self, eid):
        return next((e for e in self.entries if e["id"] == eid), None)

    def ordered_entries(self):
        return sorted(self.entries, key=lambda e: (e["date"], e["id"]))

    # ---------- ledgers ----------
    def ledger(self):
        """{account name: {'dr':[(date,ref,desc,amt)], 'cr':[...]}} - only accounts with entries."""
        led = {}
        for e in self.ordered_entries():
            for l in e["lines"]:
                s = led.setdefault(l["account"], {"dr": [], "cr": []})
                if l["dr"]: s["dr"].append((e["date"], e["ref"], l["desc"], l["dr"]))
                if l["cr"]: s["cr"].append((e["date"], e["ref"], l["desc"], l["cr"]))
        return led

    def active_accounts(self):
        led = self.ledger()
        return [a for a in self.sorted_accounts() if a["name"] in led], led

    def trial_balance(self):
        acts, led = self.active_accounts()
        rows, td, tc = [], 0.0, 0.0
        for a in acts:
            d = r2(sum(x[3] for x in led[a["name"]]["dr"])); c = r2(sum(x[3] for x in led[a["name"]]["cr"]))
            bd, bc = max(r2(d - c), 0), max(r2(c - d), 0)
            rows.append((a["code"], a["name"], a["type"], bd, bc)); td += bd; tc += bc
        return rows, r2(td), r2(tc)

    def _net(self):
        """{name: (account, signed balance on its normal side)} for accounts with a non-zero balance."""
        acts, led = self.active_accounts(); out = []
        for a in acts:
            d = sum(x[3] for x in led[a["name"]]["dr"]); c = sum(x[3] for x in led[a["name"]]["cr"])
            amt = r2(d - c) if a["type"] in DEBIT_TYPES else r2(c - d)
            if amt != 0: out.append((a, amt))
        return out

    def income_statement(self):
        sec = {s: [] for s in SECTIONS["Income"] + SECTIONS["Expense"]}
        for a, amt in self._net():
            if a["type"] in ("Income", "Expense"): sec[a["section"]].append((a["name"], amt))
        t = {k: r2(sum(x[1] for x in v)) for k, v in sec.items()}
        gross = r2(t["Revenue"] - t["Cost of sales"])
        profit = r2(gross + t["Other income"] - t["Expenses"])
        return sec, t, gross, profit

    def financial_position(self):
        names = SECTIONS["Asset"] + SECTIONS["Liability"] + SECTIONS["Equity"]
        sec = {s: [] for s in names}
        for a, amt in self._net():
            if a["type"] in ("Asset", "Liability", "Equity"): sec[a["section"]].append((a["name"], amt))
        t = {k: r2(sum(x[1] for x in v)) for k, v in sec.items()}
        profit = self.income_statement()[3]
        return sec, t, profit
