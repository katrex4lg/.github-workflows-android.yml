"""JM-ACCOUNTS SYSTEM - inventory of products and services (no GUI code in here).

AUTO_POST = True   -> every purchase / sale / adjustment ALSO writes its journal entry (connected to the books).
AUTO_POST = False  -> inventory is a separate stock list; the journal is never touched.

Stock is valued at weighted AVERAGE cost. Services have no stock: only sales are recorded for them.
"""
import datetime as dt
from jm_core import r2

from variant import AUTO_POST, VARIANT_NAME

KINDS = ("Product", "Service")
MOVE_TYPES = ("Purchase", "Sale", "Adjustment")
PAY = ("Cash", "Bank", "Credit")

# accounts used when posting to the journal (created automatically if the chart does not have them yet)
ACC = {"inventory": ("Inventory", "1300", "Asset", "Current assets"),
       "cash": ("Cash", "1000", "Asset", "Current assets"),
       "bank": ("Bank", "1100", "Asset", "Current assets"),
       "recv": ("Accounts Receivable", "1200", "Asset", "Current assets"),
       "pay": ("Accounts Payable", "2000", "Liability", "Current liabilities"),
       "sales": ("Sales Revenue", "4000", "Income", "Revenue"),
       "cogs": ("Cost of Goods Sold", "5000", "Expense", "Cost of sales")}


def num(x):
    if x is None: return 0.0
    try: return float(str(x).replace(",", "").strip() or 0)
    except ValueError: raise ValueError(f"'{x}' is not a number.")


# ---------------------------------------------------------------- items
def item(books, iid):
    return next((i for i in books.items if i["id"] == iid), None)


def item_by_name(books, name):
    return next((i for i in books.items if i["name"] == name), None)


def _check_item(books, code, name, kind, unit, cost, price, reorder, ignore=None):
    code, name = str(code).strip(), (name or "").strip()
    if not code: raise ValueError("Enter an item code.")
    if not name: raise ValueError("Enter an item name.")
    if kind not in KINDS: raise ValueError("Choose Product or Service.")
    cost, price, reorder = num(cost), num(price), num(reorder)
    if min(cost, price, reorder) < 0: raise ValueError("Amounts cannot be negative.")
    for i in books.items:
        if i is ignore: continue
        if i["code"].lower() == code.lower(): raise ValueError(f"Code {code} is already used by '{i['name']}'.")
        if i["name"].lower() == name.lower(): raise ValueError(f"An item named '{i['name']}' already exists.")
    if kind == "Service": cost, reorder = 0.0, 0.0
    return {"code": code, "name": name, "kind": kind, "unit": (unit or "").strip(), "cost": r2(cost), "price": r2(price), "reorder": reorder}


def add_item(books, code, name, kind, unit, cost, price, reorder):
    d = _check_item(books, code, name, kind, unit, cost, price, reorder)
    d["id"] = max([i["id"] for i in books.items] + [0]) + 1
    books.items.append(d); books.save(); return d


def update_item(books, iid, code, name, kind, unit, cost, price, reorder):
    it = item(books, iid)
    if not it: raise ValueError("Item not found.")
    d = _check_item(books, code, name, kind, unit, cost, price, reorder, ignore=it)
    if d["kind"] != it["kind"] and any(m["item"] == iid for m in books.moves):
        raise ValueError("This item already has stock movements, so it cannot change between Product and Service.")
    it.update(d)
    if AUTO_POST: _sync(books)                     # item name appears in the journal descriptions
    books.save()


def delete_item(books, iid):
    if any(m["item"] == iid for m in books.moves):
        raise ValueError("This item has stock movements, so it cannot be deleted.\nDelete those movements first.")
    books.items = [i for i in books.items if i["id"] != iid]; books.save()


# ---------------------------------------------------------------- costing
def recompute(books, moves):
    """Walk every movement in date order, work out the cost of what left stock (average cost) and the stock after it.
    Fills m['cogs'] (cost out), m['cost_in'] (cost in) and m['after']. Raises ValueError if stock would go negative."""
    st = {}
    for m in sorted(moves, key=lambda m: (m["date"], m["id"])):
        it = item(books, m["item"])
        if not it: raise ValueError("A movement refers to an item that no longer exists.")
        m["cogs"] = m["cost_in"] = 0.0; m["after"] = None
        if it["kind"] == "Service":
            if m["type"] != "Sale": raise ValueError(f"'{it['name']}' is a service - only sales can be recorded for it.")
            continue
        s = st.setdefault(it["id"], [0.0, 0.0])                  # [quantity, value]
        avg = (s[1] / s[0]) if s[0] > 1e-9 else it["cost"]
        q = m["qty"]
        if m["type"] == "Purchase":
            m["cost_in"] = r2(q * m["price"]); s[0] += q; s[1] += m["cost_in"]
        elif q > 0 and m["type"] == "Adjustment":
            m["cost_in"] = r2(q * avg); s[0] += q; s[1] += m["cost_in"]
        else:                                                    # Sale, or negative Adjustment
            out = abs(q)
            if out > s[0] + 1e-9:
                raise ValueError(f"Not enough stock of '{it['name']}' on {m['date']}: "
                                 f"{r2(s[0]):g} in stock, {out:g} needed.")
            m["cogs"] = r2(out * avg); s[1] -= m["cogs"]; s[0] -= out
            if s[0] <= 1e-9: s[0] = s[1] = 0.0
        m["after"] = s[0]
    return st


def stock(books, upto=None):
    """{item id: (quantity, value, average cost)} for every product (only movements dated up to `upto`, if given)."""
    st = recompute(books, [m for m in books.moves if not upto or m["date"] <= upto])
    out = {}
    for i in books.items:
        if i["kind"] != "Product": continue
        q, v = st.get(i["id"], (0.0, 0.0))
        out[i["id"]] = (q, r2(v), (v / q) if q > 1e-9 else i["cost"])
    return out


def stock_value(books):
    return r2(sum(v for _, v, _ in stock(books).values()))


def book_balance(books, name=None):
    """Balance of the Inventory account in the journal (debit - credit)."""
    name = name or ACC["inventory"][0]
    d = c = 0.0
    for e in books.entries:
        for l in e["lines"]:
            if l["account"] == name: d += l["dr"]; c += l["cr"]
    return r2(d - c)


# ---------------------------------------------------------------- movements
def move(books, mid):
    return next((m for m in books.moves if m["id"] == mid), None)


def _clean(books, d):
    it = item(books, d.get("item"))
    if not it: raise ValueError("Choose an item.")
    if not d.get("date"): raise ValueError("Pick a valid date.")
    typ = d.get("type")
    if typ not in MOVE_TYPES: raise ValueError("Choose Purchase, Sale or Adjustment.")
    q, p = num(d.get("qty")), num(d.get("price"))
    if typ == "Adjustment":
        if q == 0: raise ValueError("Enter a quantity (use a minus sign to take stock out).")
        if it["kind"] == "Service": raise ValueError("Services have no stock to adjust.")
        p = 0.0
    else:
        if q <= 0: raise ValueError("Enter a quantity above zero.")
        if p < 0: raise ValueError("The price cannot be negative.")
    if typ == "Purchase" and it["kind"] == "Service": raise ValueError("Services are not bought into stock - record sales only.")
    pay = d.get("pay") if d.get("pay") in PAY else "Cash"
    return {"date": d["date"], "item": it["id"], "type": typ, "qty": q, "price": r2(p),
            "pay": pay if typ != "Adjustment" else "", "party": (d.get("party") or "").strip(), "note": (d.get("note") or "").strip()}


def add_move(books, d):
    m = _clean(books, d)
    m["id"] = max([x["id"] for x in books.moves] + [0]) + 1; m["journal_id"] = None
    books.moves.append(m)
    try:
        recompute(books, books.moves)
        if AUTO_POST: _post(books, m)
    except ValueError:
        books.moves.remove(m); raise
    if AUTO_POST: _sync(books)
    books.save(); return m


def delete_move(books, mid):
    m = move(books, mid)
    if not m: return
    rest = [x for x in books.moves if x is not m]
    recompute(books, rest)                                         # refuses if later sales would run out of stock
    if m.get("journal_id"): books.delete_entry(m["journal_id"])
    books.moves = rest
    if AUTO_POST: _sync(books)
    books.save()


# ---------------------------------------------------------------- journal posting (automatic mode only)
def _acct(books, key):
    name, code, typ, sec = ACC[key]
    if not books.account(name):
        used = {a["code"] for a in books.accounts}
        while code in used: code = str(int(code) + 1)
        books.add_account(code, name, typ, sec)
    return name


def _pay_account(books, m, buying):
    p = m.get("pay") or "Cash"
    return _acct(books, "cash" if p == "Cash" else "bank" if p == "Bank" else ("pay" if buying else "recv"))


def _lines(books, m):
    it = item(books, m["item"]); nm = it["name"]; qty = f"{m['qty']:g}"
    desc = f"{m['type']} - {nm}" + (f" ({m['party']})" if m.get("party") else "")
    L = lambda a, d, c, t=desc: {"account": a, "desc": t, "dr": r2(d), "cr": r2(c)}
    if m["type"] == "Purchase":
        amt = r2(m["qty"] * m["price"])
        return [L(_acct(books, "inventory"), amt, 0), L(_pay_account(books, m, True), 0, amt)]
    if m["type"] == "Sale":
        amt = r2(m["qty"] * m["price"])
        out = [L(_pay_account(books, m, False), amt, 0), L(_acct(books, "sales"), 0, amt)]
        if it["kind"] == "Product" and m["cogs"]:
            out += [L(_acct(books, "cogs"), m["cogs"], 0, f"Cost of {qty} x {nm}"), L(_acct(books, "inventory"), 0, m["cogs"], f"Cost of {qty} x {nm}")]
        return out
    if m["qty"] < 0:                                               # stock lost / written off
        return [L(_acct(books, "cogs"), m["cogs"], 0), L(_acct(books, "inventory"), 0, m["cogs"])]
    return [L(_acct(books, "inventory"), m["cost_in"], 0), L(_acct(books, "cogs"), 0, m["cost_in"])]


def _post(books, m):
    lines = _lines(books, m)
    if len(lines) < 2 or any(l["dr"] == l["cr"] == 0 for l in lines):
        return                                                      # nothing worth posting (e.g. zero-value movement)
    e = books.add_entry({"date": m["date"], "ref": f"INV{m['id']}", "lines": lines})
    m["journal_id"] = e["id"]


def _sync(books):
    """Re-write the journal lines of every inventory entry (costs can change when earlier movements change)."""
    recompute(books, books.moves)
    for m in books.moves:
        e = books.entry(m["journal_id"]) if m.get("journal_id") else None
        if e:
            lines = _lines(books, m)
            if len(lines) >= 2: e["lines"] = lines; e["date"] = m["date"]
