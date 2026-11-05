"""Builds report models and renders them to PDF / Excel / print / email."""
import os, subprocess, sys, smtplib, mimetypes, webbrowser, urllib.parse
from email.message import EmailMessage
from jm_core import fmt_date, parse_date, SECTIONS, r2, APP_NAME

REPORT_NAMES = {"journal": "General Journal", "taccounts": "T-Accounts", "trial": "Trial Balance",
                "income": "Income Statement", "position": "Statement of Financial Position", "stock": "Stock Report"}
SHEET_NAMES = {"journal": "Journal", "taccounts": "T-Accounts", "trial": "Trial Balance",
               "income": "Income Statement", "position": "Financial Position", "stock": "Stock Report"}
ORDER = ["taccounts", "journal", "trial", "income", "position", "stock"]


def money(v, blank_zero=True):
    if v is None or v == "": return ""
    if blank_zero and abs(v) < 0.005: return ""
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


def period_text(books):
    d = parse_date(books.settings.get("period_end", ""))
    return d.strftime("%d %B %Y").lstrip("0") if d else ""


def default_period_end(books):
    if books.entries: return max(e["date"] for e in books.entries)
    return ""


# ---------------- model builders ----------------
# report = {key,title,subtitle,business,blocks:[{heading,columns,align,widths,rows:[(cells,style)]}]}
# styles: "" normal, "b" bold, "h" heading, "tot" bold + top rule, "grand" bold + double rule

def _base(books, key, subtitle=""):
    return {"key": key, "title": REPORT_NAMES[key], "subtitle": subtitle,
            "business": books.settings.get("business", "") or "(Business name)", "blocks": []}


def build_journal(books):
    r = _base(books, "journal"); rows = []; td = tc = 0.0
    for e in books.ordered_entries():
        for i, l in enumerate(e["lines"]):
            rows.append(([fmt_date(e["date"]) if i == 0 else "", e["ref"], ("      " if l["cr"] else "") + l["account"],
                          l["desc"], l["dr"] or None, l["cr"] or None], ""))
            td += l["dr"]; tc += l["cr"]
    rows.append((["", "", "Totals", "", r2(td), r2(tc)], "tot"))
    r["blocks"].append({"heading": None, "columns": ["Date", "Ref", "Account", "Description", "Debit", "Credit"],
                        "align": "llllrr", "widths": [11, 6, 30, 26, 12, 12], "rows": rows})
    return r


def line_kind(st, taccount=False):
    """(single line above the figure, double line below the figure) for a row style."""
    if st == "grand": return True, True
    if st == "tot": return True, bool(taccount)
    return False, False


def t_account_blocks(books, only=None):
    """One block per account that has journal entries (or just the account named in `only`)."""
    acts, led = books.active_accounts(); blocks = []
    for a in acts:
        if only and a["name"] != only: continue
        dr, cr = list(led[a["name"]]["dr"]), list(led[a["name"]]["cr"])
        td, tc = r2(sum(x[3] for x in dr)), r2(sum(x[3] for x in cr))
        bal = r2(td - tc)
        L = [(fmt_date(x[0]), x[1], x[2], x[3]) for x in dr]
        R = [(fmt_date(x[0]), x[1], x[2], x[3]) for x in cr]
        tot = max(td, tc)
        if bal > 0: R.append(("", "", "Balance c/d", bal))
        elif bal < 0: L.append(("", "", "Balance c/d", -bal))
        n = max(len(L), len(R)); rows = []
        for i in range(n):
            l = L[i] if i < len(L) else ("", "", "", None)
            rr = R[i] if i < len(R) else ("", "", "", None)
            rows.append(([l[0], l[1], l[2], l[3], rr[0], rr[1], rr[2], rr[3]], ""))
        rows.append((["", "", "Total", tot, "", "", "Total", tot], "tot"))
        if bal > 0: rows.append((["", "", "Balance b/d", bal, "", "", "", None], "b"))
        elif bal < 0: rows.append((["", "", "", None, "", "", "Balance b/d", -bal], "b"))
        blocks.append({"heading": a["name"], "center": True,
                       "sides": ("Dr", "Cr"),
                       "columns": ["Date", "Ref", "Description", "Amount", "Date", "Ref", "Description", "Amount"],
                       "align": "lllrlllr", "widths": [10, 5, 16, 10, 10, 5, 16, 10], "rows": rows, "account": a["name"]})
    return blocks


def build_taccounts(books):
    r = _base(books, "taccounts"); r["blocks"] = t_account_blocks(books); return r


def build_trial(books):
    r = _base(books, "trial", "As at " + period_text(books))
    rows, td, tc = books.trial_balance()
    out = [([n, d or None, k or None], "") for c, n, t, d, k in rows]
    out.append((["Totals", td, tc], "grand"))
    r["blocks"].append({"heading": None, "columns": ["Account", "Debit", "Credit"], "align": "lrr",
                        "widths": [44, 16, 16], "rows": out})
    return r


def _statement(r, rows):
    r["blocks"].append({"heading": None, "columns": ["Details", "Amount", "Total"], "align": "lrr",
                        "widths": [50, 16, 16], "rows": rows})


def build_income(books):
    r = _base(books, "income", "For the period ended " + period_text(books))
    sec, t, gross, profit = books.income_statement(); rows = []
    def block(name, label_total):
        if sec[name]:
            rows.append(([name, None, None], "h"))
            for n, a in sec[name]: rows.append(([n, a, None], ""))
            rows.append(([label_total, None, t[name]], "tot"))
    block("Revenue", "Net revenue")
    block("Cost of sales", "Total cost of sales")
    rows.append((["Gross profit / (loss)", None, gross], "tot"))
    block("Other income", "Total other income")
    block("Expenses", "Total expenses")
    rows.append((["Profit / (loss) for the period", None, profit], "grand"))
    _statement(r, rows); return r


def build_position(books):
    r = _base(books, "position", "As at " + period_text(books))
    sec, t, profit = books.financial_position(); rows = []
    def block(name, label_total):
        if sec[name]:
            rows.append(([name, None, None], "h"))
            for n, a in sec[name]: rows.append(([n, a, None], ""))
            rows.append(([label_total, None, t[name]], "tot"))
    block("Non-current assets", "Total non-current assets")
    block("Current assets", "Total current assets")
    ta = r2(t["Non-current assets"] + t["Current assets"])
    rows.append((["TOTAL ASSETS", None, ta], "grand"))
    rows.append((["Equity", None, None], "h"))
    for n, a in sec["Equity"]: rows.append(([n, a, None], ""))
    rows.append((["Profit / (loss) for the period", profit, None], ""))
    te = r2(t["Equity"] + profit)
    rows.append((["Total equity", None, te], "tot"))
    block("Non-current liabilities", "Total non-current liabilities")
    block("Current liabilities", "Total current liabilities")
    tl = r2(t["Non-current liabilities"] + t["Current liabilities"])
    if tl: rows.append((["Total liabilities", None, tl], "tot"))
    rows.append((["TOTAL EQUITY AND LIABILITIES", None, r2(te + tl)], "grand"))
    diff = r2(ta - te - tl)
    if diff: rows.append(([f"Out of balance by {diff:,.2f}", None, None], "b"))
    _statement(r, rows); return r


def build_stock(books):
    """Stock on hand (average cost) and the stock movements, up to the period end date."""
    import jm_inventory as INV
    pe = parse_date(books.settings.get("period_end", "")); upto = pe.isoformat() if pe else None
    r = _base(books, "stock", ("As at " + period_text(books)) if pe else "")
    try: st = INV.stock(books, upto)
    except ValueError: st = {}
    rows, total = [], 0.0
    for it in sorted(books.items, key=lambda i: str(i["code"]).lower()):
        if it["kind"] != "Product": continue
        q, v, avg = st.get(it["id"], (0.0, 0.0, it["cost"]))
        status = "OUT" if q <= 1e-9 else "LOW" if (it["reorder"] > 0 and q <= it["reorder"]) else "OK"
        rows.append(([str(it["code"]), it["name"], f"{q:g} {it['unit']}".strip(), avg, v, it["price"], status], "")); total += v
    rows.append((["", "Total stock value", "", None, r2(total), None, ""], "grand"))
    r["blocks"].append({"heading": "Stock on hand (average cost)", "columns": ["Code", "Item", "In stock", "Avg cost", "Stock value", "Sell price", "Status"],
                        "align": "llrrrrl", "widths": [8, 30, 14, 13, 15, 14, 8], "rows": rows})
    mrows = []
    for m in sorted(books.moves, key=lambda m: (m["date"], m["id"])):
        if upto and m["date"] > upto: continue
        it = INV.item(books, m["item"])
        adj = m["type"] == "Adjustment"
        mrows.append(([fmt_date(m["date"]), it["name"] if it else "?", m["type"], f"{m['qty']:g}", None if adj else m["price"],
                       None if adj else r2(m["qty"] * m["price"]), (m.get("cogs") or m.get("cost_in") or None)], ""))
    try: INV.recompute(books, books.moves)                          # leave every movement with its full-history figures
    except ValueError: pass
    r["blocks"].append({"heading": "Stock movements", "columns": ["Date", "Item", "Type", "Quantity", "Unit price", "Total", "Cost of stock"],
                        "align": "lllrrrr", "widths": [11, 30, 12, 10, 13, 15, 15], "rows": mrows or [(["", "No movements", "", "", None, None, None], "")]})
    return r


BUILDERS = {"stock": build_stock, "journal": build_journal, "taccounts": build_taccounts, "trial": build_trial,
            "income": build_income, "position": build_position}


def build_reports(books, keys):
    return [BUILDERS[k](books) for k in ORDER if k in keys]


def cell_text(v):
    if isinstance(v, (int, float)): return money(v)
    return "" if v is None else str(v)


# ---------------- PDF (reportlab) ----------------
def _make_linefig():
    from reportlab.platypus import Flowable
    from reportlab.pdfbase.pdfmetrics import stringWidth
    class LineFig(Flowable):
        """Bold figure with a single line above and/or a double line below, each exactly as long as the figure."""
        def __init__(self, text, above, below, size=11, base=0.0, align="RIGHT"):
            Flowable.__init__(self); self.text, self.above, self.below, self.size, self.base = text, above, below, size, base
            self.width = stringWidth(text, "Helvetica-Bold", size); self.height = self.base + size + 1; self.hAlign = align
        def wrap(self, aw, ah): return self.width, self.height
        def draw(self):
            c = self.canv; c.setFont("Helvetica-Bold", self.size); c.drawString(0, self.base, self.text); c.setLineWidth(0.5)
            if self.above: c.line(0, self.base + self.size + 0.2, self.width, self.base + self.size + 0.2)
            if self.below: c.line(0, 0.5, self.width, 0.5); c.line(0, 2.5, self.width, 2.5)
    return LineFig


def to_pdf_reportlab(reports, path):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    LineFig = _make_linefig()
    ss = getSampleStyleSheet()
    biz = ParagraphStyle("biz", parent=ss["Title"], fontSize=16, spaceAfter=2)
    ttl = ParagraphStyle("ttl", parent=ss["Heading2"], alignment=1, spaceAfter=0)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=11, alignment=1, textColor=colors.grey, spaceAfter=8)
    hd = ParagraphStyle("hd", parent=ss["Heading4"], fontSize=11, spaceBefore=8, spaceAfter=2)
    hdc = ParagraphStyle("hdc", parent=hd, alignment=1, fontSize=11)
    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=14*mm, rightMargin=14*mm, topMargin=14*mm, bottomMargin=14*mm,
                            title=APP_NAME, author=APP_NAME)
    story = []; W = landscape(A4)[0] - 28*mm
    for ri, rep in enumerate(reports):
        if ri: story.append(PageBreak())
        story += [Paragraph(rep["business"], biz), Paragraph(rep["title"], ttl), Paragraph(rep["subtitle"] or "&nbsp;", sub)]
        for b in rep["blocks"]:
            tw = sum(b["widths"]); cw = [W * w / tw for w in b["widths"]]
            pre = b.get("pre"); nh = 2 if pre else 1; two = len(b["align"]) == 8
            data = ([pre] if pre else []) + [b["columns"]] + [[cell_text(c) for c in cells] for cells, _ in b["rows"]]
            ts = [("FONTSIZE", (0, 0), (-1, -1), 11), ("BACKGROUND", (0, 0), (-1, nh - 1), colors.HexColor("#1F3A5F")),
                  ("TEXTCOLOR", (0, 0), (-1, nh - 1), colors.white), ("FONTNAME", (0, 0), (-1, nh - 1), "Helvetica-Bold"),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
            for ci, a_ in enumerate(b["align"]):
                ts.append(("ALIGN", (ci, 0), (ci, -1), "RIGHT" if a_ == "r" else "LEFT"))
            for i, (cells, st) in enumerate(b["rows"], start=nh):
                if st in ("b", "h", "tot", "grand"): ts.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
                if st == "h": ts.append(("TEXTCOLOR", (0, i), (-1, i), colors.HexColor("#1F3A5F")))
                above, below = line_kind(st, two)
                if above or below:
                    # every filled cell in a lined row is drawn by LineFig, so labels and figures share one baseline
                    base = 4.5 if below else 0.0
                    ts.append(("TOPPADDING", (0, i), (-1, i), 4))
                    for ci, v in enumerate(cells):
                        if not data[i][ci]: continue
                        isfig = isinstance(v, (int, float))
                        data[i][ci] = LineFig(data[i][ci], above and isfig, below and isfig, base=base,
                                              align="RIGHT" if b["align"][ci] == "r" else "LEFT")
            if two: ts.append(("LINEAFTER", (3, 0), (3, -1), 0.6, colors.black))
            t = Table(data, colWidths=cw, repeatRows=nh); t.setStyle(TableStyle(ts))
            if b["heading"] and b.get("sides"):
                hl = ParagraphStyle("hl", parent=hdc, alignment=0); hr_ = ParagraphStyle("hr", parent=hdc, alignment=2)
                hp = Table([[Paragraph(b["sides"][0], hl), Paragraph(b["heading"], hdc), Paragraph(b["sides"][1], hr_)]],
                           colWidths=[W * 0.15, W * 0.70, W * 0.15])
                hp.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))   # same 4 pt as the table, so Dr / Cr line up
            else:
                hp = Paragraph(b["heading"], hdc if b.get("center") else hd) if b["heading"] else None
            if hp is not None and (two or len(data) < 25): story.append(KeepTogether([hp, t]))   # a T-account is never split across pages
            else:
                if hp is not None: story.append(hp)
                story.append(t)
            story.append(Spacer(1, 6))
    if not story: story.append(Paragraph("No data.", ss["Normal"]))
    doc.build(story)


# ---------------- text rendering (used for Microsoft Print to PDF) ----------------
def to_text_pages(reports, width=104, per_page=62):
    """Lays every report out as pages of fixed-width text lines.
    T-accounts are never split: if one does not fit in what is left of a page it moves, whole, to the next page."""
    pages = []
    for rep in reports:
        keep = rep.get("key") == "taccounts"
        cur = [rep["business"].center(width), rep["title"].center(width), (rep["subtitle"] or "").center(width), ""]

        def put(blk, whole):
            """Add a block's lines to the current page, starting a new page when needed."""
            nonlocal cur
            if whole and len(cur) > 4 and len(cur) + len(blk) > per_page and len(blk) <= per_page:
                pages.append(cur); cur = []
            for ln in blk:
                if not cur and ln == "": continue          # no blank line at the top of a page
                cur.append(ln)
                if len(cur) >= per_page: pages.append(cur); cur = []

        for b in rep["blocks"]:
            n = len(b["columns"]); tw = sum(b["widths"]); gap = 2
            avail = width - gap * (n - 1)
            cw = [max(4, int(avail * w / tw)) for w in b["widths"]]
            order = sorted(range(n), key=lambda i: -b["widths"][i]); k = 0
            while sum(cw) < avail:                         # hand out the rounding leftovers: every row is exactly `width` wide,
                cw[order[k % n]] += 1; k += 1              # so the 'Cr' heading sits right above the right-hand amounts
            def row(cells):
                out = []
                for c, w, a in zip(cells, cw, b["align"]):
                    s = cell_text(c)[:w]; out.append(s.rjust(w) if a == "r" else s.ljust(w))
                return (" " * gap).join(out).rstrip()
            lines = []
            if b["heading"] and b.get("sides"):
                s0, s1 = b["sides"]; lines += ["", s0 + b["heading"].center(width - len(s0) - len(s1)) + s1]
            elif b["heading"]: lines += ["", b["heading"]]
            if b.get("pre"): lines.append(row(b["pre"]))
            lines.append(row(b["columns"])); lines.append("-" * width)
            def figline(cells, ch):
                return [ch * len(cell_text(c)) if isinstance(c, (int, float)) and cell_text(c) else "" for c in cells]
            for cells, st in b["rows"]:
                above, below = line_kind(st, n == 8)
                if above: lines.append(row(figline(cells, "-")))
                lines.append(row(cells))
                if below: lines.append(row(figline(cells, "=")))
            lines.append("")
            put(lines, keep)
        if cur: pages.append(cur)
    return pages


def _a4_printer_dc(printer):
    """Printer device context forced to A4 landscape (falls back to the printer's own default if that fails)."""
    import win32ui
    try:
        import win32print, win32gui, win32con
        h = win32print.OpenPrinter(printer)
        try:
            dm = win32print.GetPrinter(h, 2)["pDevMode"]
        finally:
            win32print.ClosePrinter(h)
        dm.PaperSize = win32con.DMPAPER_A4; dm.Orientation = win32con.DMORIENT_LANDSCAPE
        dm.Fields |= win32con.DM_PAPERSIZE | win32con.DM_ORIENTATION
        return win32ui.CreateDCFromHandle(win32gui.CreateDC("WINSPOOL", printer, dm))
    except Exception:
        dc = win32ui.CreateDC(); dc.CreatePrinterDC(printer); return dc


def print_to_ms_pdf(reports, path, printer="Microsoft Print to PDF"):
    """Windows only: draws the reports on the 'Microsoft Print to PDF' printer (A4), saving straight to `path`."""
    import win32ui, win32con
    COLS, FONT_PT = 110, 11.0                      # 110 characters of 11 pt Courier = 726 pt, fits A4 landscape's 842 pt
    dc = _a4_printer_dc(printer)
    dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY); dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
    page_h = dc.GetDeviceCaps(win32con.PHYSICALHEIGHT) or dc.GetDeviceCaps(win32con.VERTRES)
    font = win32ui.CreateFont({"name": "Courier New", "height": -int(FONT_PT * dpi_y / 72)})
    dc.SelectObject(font)
    page_w = dc.GetDeviceCaps(win32con.PHYSICALWIDTH) or dc.GetDeviceCaps(win32con.HORZRES)
    line_h = int(FONT_PT * dpi_y / 72 * 1.3); top = int(0.5 * dpi_y)
    left = max(int(0.3 * dpi_x), int((page_w - COLS * 0.6 * FONT_PT * dpi_x / 72) / 2))      # text block centred on the page
    per_page = max(20, int((page_h - 2 * top) / line_h) - 1)   # as many lines as really fit on the A4 page
    pages = to_text_pages(reports, width=COLS, per_page=per_page)
    dc.StartDoc(APP_NAME, path)
    try:
        for pg in pages:
            dc.StartPage(); dc.SelectObject(font)
            for i, ln in enumerate(pg): dc.TextOut(left, top + i * line_h, ln)
            dc.EndPage()
    finally:
        dc.EndDoc()
    if not os.path.exists(path): raise RuntimeError("Microsoft Print to PDF did not create the file.")


def make_pdf(reports, path):
    """Uses Microsoft Print to PDF on Windows; falls back to the built-in PDF writer. Returns the method used."""
    if sys.platform.startswith("win"):
        try:
            if os.path.exists(path): os.remove(path)
            print_to_ms_pdf(reports, path); return "Microsoft Print to PDF"
        except Exception:
            pass
    to_pdf_reportlab(reports, path); return "built-in PDF writer"


# ---------------- Excel ----------------
def to_xlsx(reports, path):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    navy = PatternFill("solid", fgColor="1F3A5F"); thin = Side(style="thin"); dbl = Side(style="double")
    for rep in reports:
        ws = wb.create_sheet(SHEET_NAMES[rep["key"]]); ncol = max(len(b["columns"]) for b in rep["blocks"]) if rep["blocks"] else 1
        ws["A1"] = rep["business"]; ws["A1"].font = Font(bold=True, size=16)
        ws["A2"] = rep["title"]; ws["A2"].font = Font(bold=True, size=13)
        ws["A3"] = rep["subtitle"]; ws["A3"].font = Font(italic=True, color="666666", size=11)
        r = 5; widths = [0] * ncol
        for b in rep["blocks"]:
            if b["heading"]:
                if b.get("sides"):
                    n_ = len(b["columns"]); s0 = ws.cell(r, 1, b["sides"][0]); s1 = ws.cell(r, n_, b["sides"][1])
                    s0.font = s1.font = Font(bold=True, color="1F3A5F", size=11); s1.alignment = Alignment(horizontal="right")
                    hc = ws.cell(r, 2, b["heading"]); hc.font = Font(bold=True, color="1F3A5F", size=11)
                    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=n_ - 1); hc.alignment = Alignment(horizontal="center")
                else:
                    hc = ws.cell(r, 1, b["heading"]); hc.font = Font(bold=True, color="1F3A5F", size=11)
                if b.get("center") and not b.get("sides"):
                    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(b["columns"])); hc.alignment = Alignment(horizontal="center")
                r += 1
            two = len(b["columns"]) == 8
            for hdr in ([b["pre"]] if b.get("pre") else []) + [b["columns"]]:
                for ci, c in enumerate(hdr, 1):
                    x = ws.cell(r, ci, c or None); x.font = Font(bold=True, color="FFFFFF", size=11); x.fill = navy
                    if two and ci == 4: x.border = Border(right=thin)
                    x.alignment = Alignment(horizontal="right" if b["align"][ci-1] == "r" else "left")
                    widths[ci-1] = max(widths[ci-1], len(c))
                r += 1
            for cells, st in b["rows"]:
                above, below = line_kind(st, two)
                for ci, v in enumerate(cells, 1):
                    x = ws.cell(r, ci, v if v not in ("",) else None); x.font = Font(size=11)
                    if isinstance(v, (int, float)): x.number_format = '#,##0.00;(#,##0.00)'; x.alignment = Alignment(horizontal="right")
                    if st in ("b", "h", "tot", "grand"): x.font = Font(bold=True, size=11, color="1F3A5F" if st == "h" else "000000")
                    fig = isinstance(v, (int, float)) and (above or below)     # lines sit on the figure cells only
                    if fig or (two and ci == 4):
                        x.border = Border(top=thin if above and fig else Side(), bottom=dbl if below and fig else Side(),
                                          right=thin if two and ci == 4 else Side())
                    widths[ci-1] = max(widths[ci-1], len(cell_text(v)))
                r += 1
            r += 1
        # figure columns are sized to the figures so the single/double lines are about as long as the figures
        fig_cols = {i for i, al in enumerate(rep["blocks"][0]["align"], 1) if al == "r"} if rep["key"] != "journal" and rep["blocks"] else set()
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = max(w + 2, 10) if i in fig_cols else min(max(w + 4, 10), 45)
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape" if rep["key"] in ("taccounts", "journal", "stock") else "portrait"
        ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0; ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    wb.save(path)


# ---------------- generate + email ----------------
def safe(s):
    return "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in s).strip() or "Business"


def generate(books, keys, want_pdf, want_xlsx, folder):
    os.makedirs(folder, exist_ok=True)
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S"); base = f"{safe(books.settings.get('business') or APP_NAME)}_{stamp}"
    reps = build_reports(books, keys); files, notes = [], []
    if want_pdf:
        p = os.path.join(folder, base + ".pdf"); notes.append("PDF via " + make_pdf(reps, p)); files.append(p)
    if want_xlsx:
        p = os.path.join(folder, base + ".xlsx"); to_xlsx(reps, p); files.append(p)
    return files, notes


def send_email(cfg, to, subject, body, files):
    """Sends through Gmail (smtp.gmail.com) using the Gmail address + App Password saved in Email settings."""
    user, pw = (cfg.get("smtp_user") or "").strip(), (cfg.get("smtp_password") or "").replace(" ", "")
    if not user or not pw:
        raise RuntimeError("NEEDS_SETUP")
    msg = EmailMessage(); msg["From"] = user; msg["To"] = to; msg["Subject"] = subject; msg.set_content(body)
    for f in files:
        ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"; mt, st = ctype.split("/", 1)
        with open(f, "rb") as fh: msg.add_attachment(fh.read(), maintype=mt, subtype=st, filename=os.path.basename(f))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=40) as s:
            s.login(user, pw); s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("Gmail refused the sign-in. Use a Google App Password (not your normal password) - see Email settings.")
    except Exception as ex:
        raise RuntimeError(f"Could not send through Gmail: {ex}")
    return f"Email sent to {to} through Gmail."
