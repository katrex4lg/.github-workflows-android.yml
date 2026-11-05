"""JM-ACCOUNTS SYSTEM for Android (Kivy).  Same accounting engine as the desktop app; new touch screen on top."""
import os, json, shutil, datetime as dt

import kivy
from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.textinput import TextInput

# The engine keeps its files in the app's private storage (set in JMApp.build before anything is opened).
import jm_core
from jm_core import Books, TYPES, SECTIONS, fmt_date, parse_date, r2, data_dir
import jm_inventory as INV
import jm_reports as R
import jm_users as U
from variant import VARIANT_NAME, AUTO_POST

NAVY = (0.12, 0.23, 0.37, 1)
BLUE = (0.25, 0.43, 0.66, 1)
RED = (0.85, 0.3, 0.25, 1)


# ============================================================ small UI helpers
def _wrap(label, pad=0):
    label.bind(size=lambda i, v: setattr(i, "text_size", (v[0] - pad, None)))


def lbl(text, height=None, **kw):
    l = Label(text=text, **kw)
    if height: l.size_hint_y = None; l.height = height
    _wrap(l)
    return l


def btn(text, cb, height=dp(46), color=None, **kw):
    b = Button(text=text, size_hint_y=None, height=height, **kw)
    if color: b.background_color = color
    b.bind(on_release=lambda *_: cb())
    return b


def row_button(text, cb, height=dp(64)):
    b = Button(text=text, size_hint_y=None, height=height, halign="left", valign="middle",
               background_color=(0.2, 0.26, 0.35, 1))
    b.bind(size=lambda i, v: setattr(i, "text_size", (v[0] - dp(20), v[1])))
    b.bind(on_release=lambda *_: cb())
    return b


def scroll_list(items, empty="Nothing here yet."):
    """items: list of (text, callback) or (text, callback, height)."""
    gl = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
    gl.bind(minimum_height=gl.setter("height"))
    if not items:
        gl.add_widget(lbl(empty, height=dp(60), halign="center", color=(0.7, 0.7, 0.7, 1)))
    for it in items:
        gl.add_widget(row_button(*it))
    sv = ScrollView(); sv.add_widget(gl)
    return sv


def popup(title, content, size=(0.94, 0.9), closable=True):
    p = Popup(title=title, content=content, size_hint=size, auto_dismiss=closable)
    p.open()
    return p


def msg(title, text):
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
    l = Label(text=text, halign="center", valign="middle")
    l.bind(size=lambda i, v: setattr(i, "text_size", (v[0], v[1])))
    box.add_widget(l)
    p = popup(title, box, size=(0.88, 0.5))
    box.add_widget(btn("OK", p.dismiss))


def confirm(title, text, yes, yes_text="Yes"):
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
    l = Label(text=text, halign="center", valign="middle")
    l.bind(size=lambda i, v: setattr(i, "text_size", (v[0], v[1])))
    box.add_widget(l)
    row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
    p = popup(title, box, size=(0.88, 0.5))
    row.add_widget(btn("Cancel", p.dismiss))
    def go():
        p.dismiss(); yes()
    row.add_widget(btn(yes_text, go, color=RED))
    box.add_widget(row)


def choose(title, options):
    """options: list of (label, callback)."""
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    p = popup(title, box, size=(0.88, min(0.9, 0.18 + 0.1 * (len(options) + 1))))
    for text, cb in options:
        def go(cb=cb):
            p.dismiss(); cb()
        box.add_widget(btn(text, go))
    box.add_widget(btn("Cancel", p.dismiss, color=(0.35, 0.35, 0.35, 1)))


def form(title, fields, on_ok, ok_text="Save", closable=True, intro=""):
    """fields: (key, label, kind, default, values).  kinds: text, pass, spin, check.
    on_ok(values) may raise ValueError - the message is shown inside the form."""
    root = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
    sv = ScrollView()
    gl = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
    gl.bind(minimum_height=gl.setter("height"))
    sv.add_widget(gl)
    if intro: gl.add_widget(lbl(intro, height=dp(48), halign="left", color=(0.8, 0.8, 0.8, 1)))
    widgets = {}
    for key, label, kind, default, values in fields:
        if kind == "check":
            r = BoxLayout(size_hint_y=None, height=dp(40))
            cb = CheckBox(active=bool(default), size_hint_x=None, width=dp(44))
            r.add_widget(cb); r.add_widget(lbl(label, halign="left", valign="middle"))
            gl.add_widget(r); widgets[key] = cb
            continue
        gl.add_widget(lbl(label, height=dp(22), halign="left", color=(0.75, 0.82, 0.95, 1)))
        if kind == "spin":
            w = Spinner(text=str(default) if default not in (None, "") else (values[0] if values else ""),
                        values=list(values), size_hint_y=None, height=dp(44))
        else:
            w = TextInput(text="" if default is None else str(default), multiline=False, password=(kind == "pass"),
                          size_hint_y=None, height=dp(44), write_tab=False)
        gl.add_widget(w); widgets[key] = w
    root.add_widget(sv)
    err = Label(text="", color=(1, 0.45, 0.4, 1), size_hint_y=None, height=dp(38), halign="center", valign="middle")
    err.bind(size=lambda i, v: setattr(i, "text_size", (v[0], v[1])))
    root.add_widget(err)
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    p = popup(title, root, closable=closable)

    def submit(*_):
        vals = {}
        for k, w in widgets.items():
            vals[k] = w.active if isinstance(w, CheckBox) else (w.text if isinstance(w, Spinner) else w.text.strip() if not w.password else w.text)
        try:
            on_ok(vals)
        except ValueError as e:
            err.text = str(e); return
        p.dismiss()
    if closable: row.add_widget(btn("Cancel", p.dismiss, color=(0.35, 0.35, 0.35, 1)))
    row.add_widget(btn(ok_text, submit, color=BLUE))
    root.add_widget(row)
    return p


def to_iso(text):
    d = parse_date(text)
    if not d: raise ValueError("Pick a valid date (dd/mm/yyyy).")
    return d.isoformat()


def today():
    return dt.date.today().strftime("%d/%m/%Y")


def money(v):
    return f"{v:,.2f}"


def share_text(title, text):
    """Android share sheet (mail, WhatsApp, Drive ...). Elsewhere: copies to the clipboard."""
    if platform == "android":
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent"); String = autoclass("java.lang.String")
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            i = Intent(); i.setAction(Intent.ACTION_SEND); i.setType("text/plain")
            i.putExtra(Intent.EXTRA_SUBJECT, String(title)); i.putExtra(Intent.EXTRA_TEXT, String(text))
            act.startActivity(Intent.createChooser(i, String(title)))
            return
        except Exception as e:
            msg("Share", f"Could not open the share sheet ({e}). The text was copied instead.")
    Clipboard.copy(text)
    if platform != "android": msg("Copied", "The text was copied to the clipboard.")


def render_report(rep):
    out = [rep["business"], rep["title"]] + ([rep["subtitle"]] if rep.get("subtitle") else []) + [""]
    for b in rep["blocks"]:
        w, al = b["widths"], b["align"]
        def fmt(cells):
            parts = []
            for c, wi, a in zip(cells, w, al):
                t = R.cell_text(c)[:wi]
                parts.append(t.rjust(wi) if a == "r" else t.ljust(wi))
            return " ".join(parts)
        total_w = sum(w) + len(w) - 1
        if b.get("heading"): out.append(b["heading"].upper())
        out += [fmt(b["columns"]), "-" * total_w]
        for cells, style in b["rows"]:
            if style == "grand": out.append("=" * total_w)
            elif style == "tot": out.append("-" * total_w)
            out.append(fmt(cells))
        out.append("")
    return "\n".join(out)


def mono_font():
    p = os.path.join(kivy.kivy_data_dir, "fonts", "RobotoMono-Regular.ttf")
    return p if os.path.exists(p) else "Roboto"


# ============================================================ the app
class JMApp(App):
    title = "JM Accounts"

    def build(self):
        os.environ["JM_DATA_DIR"] = self.user_data_dir
        Window.softinput_mode = "below_target"
        self.store = U.UserStore()
        self.books = Books(); self.books.load()
        self.session = None
        self.inv_mode = "items"
        self.rep_key = "trial"
        self.root_box = BoxLayout(orientation="vertical")
        self.show_login()
        return self.root_box

    # ---------------------------------------------------------- sign in
    def show_login(self):
        self.session = None
        self.root_box.clear_widgets()
        box = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(10))
        box.add_widget(Label(text="JM-ACCOUNTS SYSTEM", font_size=sp(24), bold=True, size_hint_y=None, height=dp(60)))
        box.add_widget(Label(text=f"Inventory: {VARIANT_NAME}", size_hint_y=None, height=dp(26), color=(0.7, 0.8, 0.95, 1)))
        self.u_in = TextInput(hint_text="Username", multiline=False, size_hint_y=None, height=dp(48), write_tab=False)
        self.p_in = TextInput(hint_text="Password", multiline=False, password=True, size_hint_y=None, height=dp(48), write_tab=False)
        self.p_in.bind(on_text_validate=lambda *_: self.do_login())
        self.login_err = Label(text="", color=(1, 0.45, 0.4, 1), size_hint_y=None, height=dp(30))
        for w in (self.u_in, self.p_in): box.add_widget(w)
        box.add_widget(self.login_err)
        box.add_widget(btn("Sign in", self.do_login, height=dp(52), color=BLUE))
        box.add_widget(Label(text="First start: admin / admin123", size_hint_y=None, height=dp(30), color=(0.6, 0.6, 0.6, 1)))
        box.add_widget(Label())
        self.root_box.add_widget(box)

    def do_login(self):
        u = self.store.authenticate(self.u_in.text.strip(), self.p_in.text)
        if not u:
            self.login_err.text = "Wrong username or password, or the account is switched off."; return
        self.session = U.Session(u)
        self.show_main()
        if u.get("must_change"): self.password_form(forced=True)

    def logout(self):
        self.show_login()

    # ---------------------------------------------------------- main frame
    def show_main(self):
        self.root_box.clear_widgets()
        bar = BoxLayout(size_hint_y=None, height=dp(44), padding=(dp(8), 0), spacing=dp(6))
        bar.add_widget(lbl(f"{self.session.display_name}  ·  {self.session.role_label}", halign="left", valign="middle"))
        bar.add_widget(btn("Log out", self.logout, height=dp(36), size_hint_x=None, width=dp(90)))
        self.root_box.add_widget(bar)
        tp = TabbedPanel(do_default_tab=False, tab_pos="bottom_mid", tab_width=dp(72))
        self.tabs = {}
        first = None
        for key, title in (("inv", "Stock"), ("acc", "Accounts"), ("jnl", "Journal"), ("rep", "Reports"), ("more", "More")):
            th = TabbedPanelItem(text=title)
            box = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))
            th.add_widget(box); tp.add_widget(th)
            self.tabs[key] = box
            first = first or th
        self.root_box.add_widget(tp)
        Clock.schedule_once(lambda dt_: tp.switch_to(first), 0)
        self.refresh()

    def refresh(self):
        for fn in (self.fill_inv, self.fill_acc, self.fill_jnl, self.fill_rep, self.fill_more):
            fn()

    def need(self, perm, what="change this"):
        if self.session.can(perm): return True
        msg("Not allowed", f"Your account cannot {what}.\nAsk the Admin to tick it for you (More > Manage users).")
        return False

    def attempt(self, fn, *a):
        try:
            fn(*a)
        except ValueError as e:
            msg("Cannot do that", str(e)); return False
        self.refresh(); return True

    # ================================================== STOCK (inventory)
    def fill_inv(self):
        box = self.tabs["inv"]; box.clear_widgets()
        b = self.books
        try:
            st = INV.stock(b)
        except ValueError:
            st = {}
        total = r2(sum(v for _, v, _ in st.values()))
        head = f"Stock value: {money(total)}"
        if AUTO_POST: head += f"   ·   Inventory account: {money(INV.book_balance(b))}"
        box.add_widget(lbl(head, height=dp(24), halign="left", color=(0.8, 0.9, 1, 1)))
        r1 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        r1.add_widget(btn("Items", lambda: self.set_inv("items"), height=dp(42), color=BLUE if self.inv_mode == "items" else (0.3, 0.3, 0.3, 1)))
        r1.add_widget(btn("Movements", lambda: self.set_inv("moves"), height=dp(42), color=BLUE if self.inv_mode == "moves" else (0.3, 0.3, 0.3, 1)))
        box.add_widget(r1)
        r2_ = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        r2_.add_widget(btn("+ Item", lambda: self.item_form(None), height=dp(42)))
        for t in INV.MOVE_TYPES:
            r2_.add_widget(btn("+ " + t[:6], lambda t=t: self.move_form(t), height=dp(42)))
        box.add_widget(r2_)
        rows = []
        if self.inv_mode == "items":
            for it in sorted(b.items, key=lambda i: str(i["code"]).lower()):
                if it["kind"] == "Product":
                    q, v, avg = st.get(it["id"], (0.0, 0.0, it["cost"]))
                    flag = "  [OUT]" if q <= 1e-9 else "  [LOW]" if (it["reorder"] > 0 and q <= it["reorder"]) else ""
                    t = f"{it['code']}  {it['name']}{flag}\nIn stock {q:g} {it['unit']}  ·  value {money(v)}  ·  price {money(it['price'])}"
                else:
                    t = f"{it['code']}  {it['name']}  (Service)\nprice {money(it['price'])}"
                rows.append((t, lambda it=it: self.item_menu(it)))
            box.add_widget(scroll_list(rows, "No items yet. Tap + Item."))
        else:
            for m in sorted(b.moves, key=lambda m: (m["date"], m["id"]), reverse=True):
                it = INV.item(b, m["item"])
                nm = it["name"] if it else "?"
                adj = m["type"] == "Adjustment"
                t = f"{fmt_date(m['date'])}  {m['type']}  {nm}\nQty {m['qty']:g}" + ("" if adj else f" @ {money(m['price'])}  =  {money(m['qty'] * m['price'])}") + \
                    (f"  ·  {m['pay']}" if m.get("pay") else "") + (f"  ·  {m['party']}" if m.get("party") else "")
                rows.append((t, lambda m=m: self.move_menu(m)))
            box.add_widget(scroll_list(rows, "No stock movements yet."))

    def set_inv(self, mode):
        self.inv_mode = mode; self.fill_inv()

    def item_menu(self, it):
        opts = [("Edit item", lambda: self.item_form(it)), ("Delete item", lambda: self.item_delete(it))]
        opts.insert(0, ("Record a sale", lambda: self.move_form("Sale", it)))
        if it["kind"] == "Product":
            opts.insert(0, ("Record a purchase", lambda: self.move_form("Purchase", it)))
        choose(f"{it['code']}  {it['name']}", opts)

    def item_form(self, it):
        if not self.need("inventory", "change inventory"): return
        fields = [("code", "Item code", "text", it["code"] if it else "", None),
                  ("name", "Item name", "text", it["name"] if it else "", None),
                  ("kind", "Type", "spin", it["kind"] if it else "Product", INV.KINDS),
                  ("unit", "Unit (pcs, kg ...)", "text", it["unit"] if it else "", None),
                  ("cost", "Cost price (Products)", "text", f"{it['cost']:g}" if it else "0", None),
                  ("price", "Selling price", "text", f"{it['price']:g}" if it else "0", None),
                  ("reorder", "Reorder level (Products)", "text", f"{it['reorder']:g}" if it else "0", None)]
        def ok(v):
            args = (v["code"], v["name"], v["kind"], v["unit"], v["cost"], v["price"], v["reorder"])
            if it: INV.update_item(self.books, it["id"], *args)
            else: INV.add_item(self.books, *args)
            self.refresh()
        form("Edit item" if it else "New item", fields, ok)

    def item_delete(self, it):
        if not self.need("inventory", "change inventory"): return
        confirm("Delete item", f"Delete '{it['name']}'?", lambda: self.attempt(INV.delete_item, self.books, it["id"]))

    def move_form(self, typ, it=None):
        if not self.need("inventory", "change inventory"): return
        pool = [i for i in self.books.items if typ == "Sale" or i["kind"] == "Product"]
        if not pool:
            msg("No items", "Add an item first (+ Item)." if typ == "Sale" else "Add a Product first (+ Item)."); return
        label = lambda i: f"{i['code']} - {i['name']}"
        byname = {label(i): i for i in pool}
        start = label(it) if it and label(it) in byname else label(pool[0])
        fields = [("item", "Item", "spin", start, list(byname)),
                  ("date", "Date (dd/mm/yyyy)", "text", today(), None),
                  ("qty", "Quantity" + (" (minus = take out)" if typ == "Adjustment" else ""), "text", "", None)]
        if typ != "Adjustment":
            dflt = ""
            if it: dflt = f"{(it['cost'] if typ == 'Purchase' else it['price']):g}"
            fields += [("price", "Unit " + ("cost" if typ == "Purchase" else "price"), "text", dflt, None),
                       ("pay", "Paid by", "spin", "Cash", INV.PAY),
                       ("party", "Supplier" if typ == "Purchase" else "Customer", "text", "", None)]
        fields.append(("note", "Note", "text", "", None))
        def ok(v):
            d = {"item": byname[v["item"]]["id"], "date": to_iso(v["date"]), "type": typ, "qty": v["qty"],
                 "price": v.get("price", 0), "pay": v.get("pay", ""), "party": v.get("party", ""), "note": v["note"]}
            INV.add_move(self.books, d)
            self.refresh()
        form("New " + typ.lower(), fields, ok)

    def move_menu(self, m):
        it = INV.item(self.books, m["item"])
        extra = "\n(its journal entry is deleted too)" if m.get("journal_id") else ""
        choose(f"{m['type']}  {it['name'] if it else '?'}",
               [("Delete this movement", lambda: self.move_delete(m, extra))])

    def move_delete(self, m, extra):
        if not self.need("inventory", "change inventory"): return
        confirm("Delete movement", "Delete this stock movement?" + extra, lambda: self.attempt(INV.delete_move, self.books, m["id"]))

    # ================================================== ACCOUNTS
    def fill_acc(self):
        box = self.tabs["acc"]; box.clear_widgets()
        box.add_widget(btn("+ Add account", lambda: self.acc_form(None)))
        rows = [(f"{a['code']}   {a['name']}\n{a['type']}  ·  {a['section']}", lambda a=a: self.acc_menu(a))
                for a in self.books.sorted_accounts()]
        box.add_widget(scroll_list(rows, "No accounts."))

    def acc_menu(self, a):
        choose(f"{a['code']}  {a['name']}", [("Edit account", lambda: self.acc_form(a)), ("Delete account", lambda: self.acc_delete(a))])

    def acc_form(self, a):
        if not self.need("accounts", "edit the Chart of Accounts"): return
        sections = [s for t in TYPES for s in SECTIONS[t]]
        fields = [("code", "Code", "text", a["code"] if a else "", None),
                  ("name", "Account name", "text", a["name"] if a else "", None),
                  ("type", "Type", "spin", a["type"] if a else "Asset", TYPES),
                  ("section", "Section (must belong to the type)", "spin", a["section"] if a else "Current assets", sections)]
        def ok(v):
            if a: self.books.update_account(a["name"], v["code"], v["name"], v["type"], v["section"])
            else: self.books.add_account(v["code"], v["name"], v["type"], v["section"])
            self.refresh()
        form("Edit account" if a else "New account", fields, ok)

    def acc_delete(self, a):
        if not self.need("accounts", "edit the Chart of Accounts"): return
        confirm("Delete account", f"Delete '{a['name']}'?", lambda: self.attempt(self.books.delete_account, a["name"]))

    # ================================================== JOURNAL
    def inv_managed(self, e):
        return AUTO_POST and any(m.get("journal_id") == e["id"] for m in self.books.moves)

    def fill_jnl(self):
        box = self.tabs["jnl"]; box.clear_widgets()
        box.add_widget(btn("+ New journal entry", lambda: self.jnl_form(None)))
        rows = []
        for e in reversed(self.books.ordered_entries()):
            tot = r2(sum(l["dr"] for l in e["lines"]))
            first = e["lines"][0]["desc"] if e["lines"] else ""
            rows.append((f"{fmt_date(e['date'])}   {e['ref']}   {money(tot)}\n{first}", lambda e=e: self.jnl_menu(e)))
        box.add_widget(scroll_list(rows, "No journal entries."))

    def jnl_text(self, e):
        lines = [f"{fmt_date(e['date'])}   Ref {e['ref']}", ""]
        for l in e["lines"]:
            lines.append(f"{'    ' if l['cr'] else ''}{l['account']}   {money(l['dr']) if l['dr'] else ''}{money(l['cr']) if l['cr'] else ''}"
                         f"{'  (Cr)' if l['cr'] else '  (Dr)'}" + (f"\n    {l['desc']}" if l["desc"] else ""))
        return "\n".join(lines)

    def jnl_menu(self, e):
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        l = Label(text=self.jnl_text(e), halign="left", valign="top")
        l.bind(size=lambda i, v: setattr(i, "text_size", (v[0], v[1])))
        box.add_widget(l)
        p = popup("Journal entry", box, size=(0.94, 0.7))
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        row.add_widget(btn("Close", p.dismiss, color=(0.35, 0.35, 0.35, 1)))
        if self.inv_managed(e):
            box.add_widget(lbl("Written automatically by Stock - delete the stock movement to remove it.", height=dp(44), halign="center", color=(0.9, 0.8, 0.5, 1)))
        else:
            def ed(): p.dismiss(); self.jnl_form(e)
            def de(): p.dismiss(); self.jnl_delete(e)
            row.add_widget(btn("Edit", ed)); row.add_widget(btn("Delete", de, color=RED))
        box.add_widget(row)

    def jnl_form(self, e):
        if not self.need("journal", "edit the General Journal"): return
        names = [a["name"] for a in self.books.sorted_accounts()]
        if not names:
            msg("No accounts", "Add accounts first."); return
        n = max(4, len(e["lines"]) if e else 4)
        root = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        sv = ScrollView(); gl = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
        gl.bind(minimum_height=gl.setter("height")); sv.add_widget(gl)
        date_in = TextInput(text=fmt_date(e["date"]) if e else today(), multiline=False, size_hint_y=None, height=dp(44))
        ref_in = TextInput(text=e["ref"] if e else self.books.next_ref(), multiline=False, size_hint_y=None, height=dp(44))
        for t, w in (("Date (dd/mm/yyyy)", date_in), ("Ref", ref_in)):
            gl.add_widget(lbl(t, height=dp(22), halign="left", color=(0.75, 0.82, 0.95, 1))); gl.add_widget(w)
        lines = []
        for i in range(n):
            ln = e["lines"][i] if e and i < len(e["lines"]) else None
            gl.add_widget(lbl(f"Line {i + 1}", height=dp(22), halign="left", color=(0.75, 0.82, 0.95, 1)))
            sp_ = Spinner(text=ln["account"] if ln else "(none)", values=["(none)"] + names, size_hint_y=None, height=dp(44))
            r = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
            dr = TextInput(text=f"{ln['dr']:g}" if ln and ln["dr"] else "", hint_text="Debit", multiline=False)
            cr = TextInput(text=f"{ln['cr']:g}" if ln and ln["cr"] else "", hint_text="Credit", multiline=False)
            r.add_widget(dr); r.add_widget(cr)
            ds = TextInput(text=ln["desc"] if ln else "", hint_text="Description", multiline=False, size_hint_y=None, height=dp(44))
            for w in (sp_, r, ds): gl.add_widget(w)
            lines.append((sp_, dr, cr, ds))
        root.add_widget(sv)
        err = Label(text="", color=(1, 0.45, 0.4, 1), size_hint_y=None, height=dp(38))
        err.bind(size=lambda i, v: setattr(i, "text_size", (v[0], v[1])))
        root.add_widget(err)
        p = popup("Edit entry" if e else "New journal entry", root)
        def num(t):
            try: return float(t.replace(",", "").strip() or 0)
            except ValueError: raise ValueError(f"'{t}' is not a number.")
        def save():
            try:
                ls = []
                for sp_, dr, cr, ds in lines:
                    acct = "" if sp_.text == "(none)" else sp_.text
                    ls.append({"account": acct, "desc": ds.text, "dr": num(dr.text), "cr": num(cr.text)})
                entry = {"date": to_iso(date_in.text), "ref": ref_in.text, "lines": ls}
                if e: self.books.update_entry(e["id"], entry)
                else: self.books.add_entry(entry)
            except ValueError as ex:
                err.text = str(ex); return
            p.dismiss(); self.refresh()
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(btn("Cancel", p.dismiss, color=(0.35, 0.35, 0.35, 1))); row.add_widget(btn("Save", save, color=BLUE))
        root.add_widget(row)

    def jnl_delete(self, e):
        if not self.need("journal", "edit the General Journal"): return
        confirm("Delete entry", f"Delete journal entry {e['ref']}?", lambda: self.attempt(self.books.delete_entry, e["id"]))

    # ================================================== REPORTS
    def fill_rep(self):
        box = self.tabs["rep"]; box.clear_widgets()
        names = [R.REPORT_NAMES[k] for k in R.ORDER]
        rev = {R.REPORT_NAMES[k]: k for k in R.ORDER}
        sp_ = Spinner(text=R.REPORT_NAMES[self.rep_key], values=names, size_hint_y=None, height=dp(44))
        sp_.bind(text=lambda i, v: self.set_rep(rev[v]))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row.add_widget(sp_)
        text = ""
        try:
            text = render_report(R.BUILDERS[self.rep_key](self.books))
        except Exception as ex:
            text = f"Could not build this report:\n{ex}"
        row.add_widget(btn("Share", lambda: share_text(R.REPORT_NAMES[self.rep_key], text), height=dp(44), size_hint_x=None, width=dp(90)))
        box.add_widget(row)
        pe = self.books.settings.get("period_end", "")
        box.add_widget(lbl(f"Period end: {pe or 'not set (More > Business settings)'}", height=dp(22), halign="left", color=(0.7, 0.7, 0.7, 1)))
        sv = ScrollView(do_scroll_x=True, do_scroll_y=True, bar_width=dp(4))
        lb = Label(text=text, font_name=mono_font(), font_size=sp(11), size_hint=(None, None), halign="left", valign="top", padding=(dp(4), dp(4)))
        lb.bind(texture_size=lambda i, v: setattr(i, "size", (max(v[0], Window.width), v[1])))
        sv.add_widget(lb)
        box.add_widget(sv)

    def set_rep(self, key):
        if key != self.rep_key:
            self.rep_key = key; self.fill_rep()

    # ================================================== MORE
    def fill_more(self):
        box = self.tabs["more"]; box.clear_widgets()
        rows = [("Business settings\nBusiness name and period end date", self.settings_form),
                ("Back up now\nSave a copy of your books on this phone", self.backup_now),
                ("Share backup\nSend your whole books as text (mail, WhatsApp, Drive)", self.share_backup),
                ("Restore from a saved backup", self.restore_menu),
                ("Restore from clipboard\nPaste a shared backup, then tap this", self.restore_clipboard),
                ("Change my password", lambda: self.password_form(False)),
                ("Change my username", self.username_form)]
        if self.session.is_admin:
            rows.append(("Manage users\nAdd people, set roles and permissions", self.users_menu))
        rows.append((f"About\nInventory: {VARIANT_NAME}", self.about))
        box.add_widget(scroll_list(rows))

    def about(self):
        msg("About", f"JM-ACCOUNTS SYSTEM (Android)\nInventory: {VARIANT_NAME}\n\nData file:\n{self.books.path}")

    # ---- settings
    def settings_form(self):
        if not self.need("settings", "change settings"): return
        s = self.books.settings
        fields = [("business", "Business name", "text", s.get("business", ""), None),
                  ("period_end", "Period end (dd/mm/yyyy)", "text", s.get("period_end", "") or R.default_period_end(self.books) and fmt_date(R.default_period_end(self.books)), None)]
        def ok(v):
            pe = v["period_end"]
            if pe and not parse_date(pe): raise ValueError("Pick a valid period end date (dd/mm/yyyy).")
            s["business"] = v["business"]; s["period_end"] = parse_date(pe).strftime("%d/%m/%Y") if pe else ""
            self.books.save(); self.refresh()
        form("Business settings", fields, ok)

    # ---- backup / restore
    def backup_dir(self):
        d = os.path.join(data_dir(), "backups"); os.makedirs(d, exist_ok=True); return d

    def backup_now(self):
        self.books.save()
        name = "jm_backup_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        shutil.copyfile(self.books.path, os.path.join(self.backup_dir(), name))
        msg("Backed up", f"Saved as\n{name}\n\nTip: use 'Share backup' too, so a copy lives outside this phone.")

    def share_backup(self):
        self.books.save()
        share_text("JM-ACCOUNTS backup " + today(), json.dumps(self.books.to_dict(), ensure_ascii=False))

    def _restore(self, d):
        if not self.need("settings", "restore a backup"): return
        if not isinstance(d, dict) or "accounts" not in d or "entries" not in d:
            raise ValueError("That does not look like a JM-ACCOUNTS backup.")
        self.books._from_dict(d); self.books.save(); self.refresh()
        msg("Restored", f"Restored {len(self.books.accounts)} accounts and {len(self.books.entries)} journal entries.")

    def restore_menu(self):
        if not self.need("settings", "restore a backup"): return
        files = sorted(f for f in os.listdir(self.backup_dir()) if f.endswith(".json"))[::-1]
        def pick(f):
            def go():
                try: self._restore(json.load(open(os.path.join(self.backup_dir(), f), encoding="utf-8")))
                except (ValueError, OSError) as e: msg("Cannot restore", str(e))
            confirm("Restore", f"Replace your current books with\n{f}?", go, "Restore")
        box = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))
        p = popup("Saved backups", box)
        box.add_widget(scroll_list([(f, lambda f=f: (p.dismiss(), pick(f))) for f in files], "No saved backups yet."))
        box.add_widget(btn("Close", p.dismiss, color=(0.35, 0.35, 0.35, 1)))

    def restore_clipboard(self):
        if not self.need("settings", "restore a backup"): return
        def go():
            try: self._restore(json.loads(Clipboard.paste()))
            except json.JSONDecodeError: msg("Cannot restore", "The clipboard does not hold a backup. Copy the shared backup text first.")
            except ValueError as e: msg("Cannot restore", str(e))
        confirm("Restore", "Replace your current books with the backup text on the clipboard?", go, "Restore")

    # ---- my account
    def password_form(self, forced=False):
        fields = ([] if forced else [("old", "Current password", "pass", "", None)]) + \
                 [("new", "New password (6+ characters)", "pass", "", None), ("new2", "Repeat new password", "pass", "", None)]
        def ok(v):
            if not forced and not self.store.authenticate(self.session.username, v["old"]): raise ValueError("The current password is wrong.")
            if v["new"] != v["new2"]: raise ValueError("The two passwords are different.")
            if v["new"] == "admin123": raise ValueError("Choose a password other than the default.")
            self.store.set_password(self.session.username, v["new"])
        form("Choose your own password" if forced else "Change password", fields, ok, closable=not forced,
             intro="You must choose your own password before you continue." if forced else "")

    def username_form(self):
        def ok(v):
            self.session.username = self.store.rename_user(self.session.username, v["name"])
        form("Change username", [("name", "New username", "text", self.session.username, None)], ok)

    # ---- users (admin)
    def users_menu(self):
        box = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))
        p = popup("Users", box)
        def rebuild():
            box.clear_widgets()
            box.add_widget(btn("+ Add user", lambda: self.user_form(None, rebuild)))
            rows = [(f"{u['username']}  ({u.get('name', '')})\n{'Admin' if u['role'] == 'admin' else 'Staff'}  ·  {'active' if u.get('active', True) else 'switched off'}",
                     lambda u=u: self.user_menu(u, rebuild)) for u in self.store.users]
            box.add_widget(scroll_list(rows))
            box.add_widget(btn("Close", p.dismiss, color=(0.35, 0.35, 0.35, 1)))
        rebuild()

    def user_menu(self, u, rebuild):
        choose(u["username"], [("Edit role and permissions", lambda: self.user_form(u, rebuild)),
                               ("Reset password", lambda: self.reset_form(u)),
                               ("Delete user", lambda: confirm("Delete user", f"Delete '{u['username']}'?", lambda: self._del_user(u, rebuild)))])

    def _del_user(self, u, rebuild):
        try: self.store.delete_user(u["username"], self.session.username)
        except ValueError as e: msg("Cannot delete", str(e)); return
        rebuild()

    def reset_form(self, u):
        def ok(v):
            self.store.set_password(u["username"], v["pw"], must_change=True)
        form(f"Reset password: {u['username']}", [("pw", "Temporary password (6+ characters)", "pass", "", None)], ok,
             intro="They will be made to choose their own at next sign-in.")

    def user_form(self, u, rebuild):
        fields = []
        if not u: fields += [("username", "Username", "text", "", None)]
        fields += [("name", "Full name", "text", u.get("name", "") if u else "", None)]
        if not u: fields += [("pw", "Temporary password (6+ characters)", "pass", "", None)]
        fields += [("role", "Role", "spin", u["role"] if u else "staff", ["admin", "staff"]),
                   ("active", "Account is active", "check", u.get("active", True) if u else True, None)]
        fields += [("perm_" + k, "Staff may: " + label, "check", bool(u) and k in u.get("perms", []), None) for k, label in U.PERMS]
        def ok(v):
            perms = [k for k, _ in U.PERMS if v["perm_" + k]]
            if u: self.store.update_user(u["username"], v["name"], v["role"], perms, v["active"])
            else: self.store.add_user(v["username"], v["name"], v["pw"], v["role"], perms, v["active"])
            rebuild()
        form("Edit user" if u else "New user", fields, ok)


if __name__ == "__main__":
    JMApp().run()
