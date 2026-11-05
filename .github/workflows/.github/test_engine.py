import os, sys, tempfile, importlib
variant = os.environ.get("JM_VARIANT", "A")
os.environ["JM_DATA_DIR"] = tempfile.mkdtemp()
import jm_core, jm_inventory as INV, jm_reports as R, jm_users as U
b = jm_core.Books(); b.load()
print(variant, "accounts", len(b.accounts), "entries", len(b.entries), "file", os.path.basename(b.path))
n0 = len(b.entries)
it = INV.add_item(b, "P1", "Widget", "Product", "pcs", 5, 9, 2)
sv = INV.add_item(b, "S1", "Repair", "Service", "", 0, 50, 0)
INV.add_move(b, {"item": it["id"], "date": "2026-11-01", "type": "Purchase", "qty": 10, "price": 5, "pay": "Cash"})
INV.add_move(b, {"item": it["id"], "date": "2026-11-02", "type": "Sale", "qty": 4, "price": 9, "pay": "Credit"})
INV.add_move(b, {"item": sv["id"], "date": "2026-11-02", "type": "Sale", "qty": 1, "price": 50, "pay": "Bank"})
try: INV.add_move(b, {"item": it["id"], "date": "2026-11-03", "type": "Sale", "qty": 99, "price": 9}); print("BUG: oversell allowed")
except ValueError as e: print("oversell refused OK")
print("stock", INV.stock(b)[it["id"]], "journal entries added:", len(b.entries) - n0)
b.settings["period_end"] = "03/11/2026"
for k in R.ORDER:
    rep = R.BUILDERS[k](b)
    for bl in rep["blocks"]:
        assert "widths" in bl and "align" in bl and "columns" in bl, (k, bl.keys())
print("all reports build OK")
s = U.UserStore(); u = s.authenticate("admin", "admin123"); print("admin login", bool(u), "must_change", u["must_change"])
s.add_user("sam", "Sam", "secret1", "staff", ["inventory"]); print("staff can inventory:", U.Session(s.user("sam")).can("inventory"), "journal:", U.Session(s.user("sam")).can("journal"))
