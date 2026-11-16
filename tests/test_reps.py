"""Sales reps evaluation on synthetic data (no real data)."""
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fsapp.system import rep_data as D  # noqa: E402
from fsapp.system import render  # noqa: E402
from fsapp.system import reps as RP  # noqa: E402
from fsapp.system.db import CompanyDB  # noqa: E402


def items_report(rows):
    """Items-by-rep report as the system exports it."""
    head = ["رقم الصنف", "اسم الصنف", "صافي الفاتورة بالمحلي", "التكلفة", "هامش الربح - مبلغ", "نسبة الربح - نسبة(%)",
            "اسم المندوب :"]
    return [head] + [[code, name, net, cost, net - cost, None, rep] for code, name, net, cost, rep in rows]


def customers_report(rows):
    head = ["رقم المندوب", "اسم المندوب", "صافي الفاتورة بالمحلي", "التكلفة", "هامش الربح - مبلغ", "نسبة", "اسم المندوب :"]
    return [head] + [[no, name, net, cost, net - cost, None, rep] for no, name, net, cost, rep in rows]


@pytest.fixture()
def db(tmp_path):
    db = CompanyDB(str(tmp_path / "reps.fsdb"))
    a, b = "1001-مندوب أول", "1002-مندوب ثاني"
    for month, f in (("2026-01", 1.0), ("2026-02", 1.5)):
        kind, rows = D.parse_rep_sales(items_report([
            ("I1", "صنف 1", 60000 * f, 42000 * f, a), ("I2", "صنف 2", 40000 * f, 30000 * f, a),
            ("I1", "صنف 1", 30000 * f, 20000 * f, b), ("I3", "صنف 3", 1000 * f, 1200 * f, b),
            ("I9", "إيجار", 5000, 0, "4000-رئيسي")]))
        assert kind == "items"
        db.save_rep_sales(kind, month, month, rows)
    kind, rows = D.parse_rep_sales(customers_report([
        ("C1", "شركة الأولى", 150000, 108000, a), ("C2", "مؤسسة الثانية", 76000, 51000, b),
        ("C3", "شركة مشتركة", 1500, 1000, b), ("C3", "شركة مشتركة", 100000, 76500, a)]))
    assert kind == "customers"
    db.save_rep_sales(kind, "2026-01", "2026-02", rows)
    db.save_reps([
        {"code": "1001", "name": "مندوب أول", "nationality": "سعودي", "salary": 7000, "target": 100000, "other": 0,
         "active": 1, "note": ""},
        {"code": "1002", "name": "مندوب ثاني", "nationality": "مقيم", "salary": 3000, "target": 50000, "other": 0,
         "active": 1, "note": ""},
        {"code": "4000", "name": "رئيسي", "nationality": "", "salary": 0, "target": 0, "other": 0, "active": 0,
         "note": ""}])
    db.save_commissions("2026-01", {"1001": 1000, "1002": 400})
    # customers' balances (aging) at the end of December and February
    db.save_aging("customers", "2025-12", [
        {"no": "C1", "name": "شركة الأولى", "rep": "1001-مندوب أول", "ctype": "آجل", "b0": 50000, "b1": 0, "b2": 0,
         "b3": 0, "b4": 0},
        {"no": "C2", "name": "مؤسسة الثانية", "rep": "مندوب ثاني", "ctype": "آجل", "b0": 20000, "b1": 0, "b2": 0,
         "b3": 0, "b4": 0}])
    db.save_aging("customers", "2026-02", [
        {"no": "C1", "name": "شركة الأولى", "rep": "1001-مندوب أول", "ctype": "آجل", "b0": 30000, "b1": 10000, "b2": 0,
         "b3": 0, "b4": 0},
        {"no": "C2", "name": "مؤسسة الثانية", "rep": "مندوب ثاني", "ctype": "آجل", "b0": 5000, "b1": 0, "b2": 15000,
         "b3": 0, "b4": 0}])
    # invoices with customer names only; receipts with the customer number in the analytic account
    inv = [["رقم الفاتورة", "نوع الفاتورة", "تاريخ الفاتورة", "رقم الحساب", "اسم الحساب", "صافي الفاتورة", "التكلفة"],
           ["2611301001", "آجل", "05/01/2026", "1140101", "شركة الأولى", 20000, 14000],
           ["2611301002", "نقد", "06/01/2026", "1110101", "شركة  الاولى", 1000, 700],
           ["2611302001", "من حساب", "07/02/2026", "1140122", "مؤسسة الثانية", 30000, 21000],
           ["2611302002", "آجل", "20/02/2026", "1140101", "شركة مشتركة", 500, 300]]
    by, info = D.parse_invoices(inv)
    db.save_invoices(by)
    rec = [["رقم السند", "تاريخ السند", "نوع السند", "رقم المرجع", "الصندوق/البنك", "العملة", "رقم الحساب", "اسم الحساب",
            "العملة", "الحساب التحليلي", "المبلغ"],
           [1, "15/01/2026", "نقداً", 1, "صندوق", "SAR", 1140101, "شركة الأولى", "SAR", "C1", 30000],
           # Excel turned 10/02/2026 into 2 October — the real date is 10 February
           [2, datetime.datetime(2026, 10, 2), "تحويل", 2, "بنك", "SAR", 1140122, "مؤسسة الثانية", "SAR", "C2", 25000],
           [3, "11/02/2026", "نقداً", 3, "صندوق", "SAR", 1110101, "صندوق مندوب أول", "SAR", "1001", 9999]]
    by, info = D.parse_receipts(rec)
    assert info["fixed_dates"] == 1 and set(by) == {"2026-01", "2026-02"}
    db.save_receipts(by)
    return db


def test_read_dates_swaps_excel_dates_back():
    vals = ["14/10/2026", datetime.datetime(2026, 1, 10), datetime.datetime(2026, 8, 10), "31/10/2026"]
    dates, n = D.read_dates(vals)
    assert n == 2 and dates[1] == datetime.date(2026, 10, 1) and dates[2] == datetime.date(2026, 10, 8)
    real = [datetime.datetime(2026, 1, 10), datetime.datetime(2026, 2, 3)]
    assert D.read_dates(real) == ([datetime.date(2026, 1, 10), datetime.date(2026, 2, 3)], 0)


def test_split_and_months():
    assert D.split_rep("4002-سلطان العمودي") == ("4002", "سلطان العمودي")
    assert D.month_of("2026-3") == "2026-03" and D.month_of("عمولة") is None
    by = {"2026-10": [1] * 95, "2026-09": [1] * 5}
    assert D.dominant(by) == ("2026-10", 0.95)
    assert len(D.merge_into(by, "2026-10")["2026-10"]) == 100


def test_pick_blocks_never_counts_a_month_twice():
    rows = [{"p_from": "2026-01", "p_to": "2026-03", "v": 1}, {"p_from": "2026-01", "p_to": "2026-01", "v": 2},
            {"p_from": "2026-04", "p_to": "2026-04", "v": 3}, {"p_from": "2026-03", "p_to": "2026-05", "v": 4}]
    got, covered, outside = RP.pick_blocks(rows, ["2026-01", "2026-02", "2026-03", "2026-04"])
    assert sorted(r["v"] for r in got) == [1, 3] and covered == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert outside == [("2026-03", "2026-05")]
    got, covered, _ = RP.pick_blocks(rows, ["2026-01"])
    assert [r["v"] for r in got] == [2]


def test_evaluation(db):
    ev = RP.evaluate(db, ["2026-01", "2026-02"])
    a, b = ev.reps["1001"], ev.reps["1002"]
    # sales from the items files (the main account is not evaluated)
    assert a.net == pytest.approx(250000) and b.net == pytest.approx(77500)
    assert "4000" not in {r.code for r in ev.evaluated()}
    # cost: salary × 2 months, iqama only for the non-Saudi, insurance for both; the commission is not counted
    assert a.rep_cost == pytest.approx(14000 + 500 / 12 * 2)
    assert b.rep_cost == pytest.approx(6000 + 10350 / 12 * 2 + 500 / 12 * 2)
    assert a.commission == 1000
    # collections: customer receipts only (the rep's cash box deposit is left out), owner from the aging
    assert a.collected == 30000 and b.collected == 25000
    assert any("1110101" in k for k in ev.excluded)
    assert a.closing == 40000 and b.closing == 20000 and b.overdue == 15000
    assert a.coll_rate == pytest.approx(30000 / 70000)
    # invoices linked by name (spaces and alef forms ignored); a shared customer goes to the rep of its branch
    assert a.inv_count == 2 and b.inv["من حساب"][0] == 1
    assert ev.inv_unlinked[0] == 0
    # scores: five criteria, each at most its weight, ranked
    assert ev.use_coll
    for r in (a, b):
        assert 0 < r.score <= 100 and sum(r.parts.values()) == pytest.approx(r.score, abs=0.1)
    assert {a.rank, b.rank} == {1, 2}
    # balance check: opening + credit invoices − receipts = closing
    rec = {x["no"]: x for x in ev.reconciliation()}
    assert rec["C1"]["diff"] == pytest.approx(40000 - (50000 + 20000 - 30000))
    assert rec["C2"]["diff"] == pytest.approx(20000 - (20000 + 30000 - 25000))


def test_without_aging_collection_is_left_out(db):
    db.con.execute("DELETE FROM customers")
    ev = RP.evaluate(db, ["2026-01", "2026-02"])
    assert not ev.use_coll and "coll" not in ev.reps["1001"].parts
    assert sum(w for _, _, w in ev.weights_used()) == pytest.approx(1)
    assert any("أعمار العملاء" in n for n in ev.notes)


def test_range_file_not_split(db):
    ev = RP.evaluate(db, ["2026-02"])
    assert ev.reps["1001"].net == pytest.approx(150000)       # the February items file
    assert any("يتعدى حدود الفترة" in n for n in ev.notes)   # the Jan–Feb customers file is not used


def test_reports_render(db):
    ev = RP.evaluate(db, ["2026-01", "2026-02"])
    reps = [RP.rpt_summary(ev), RP.rpt_rep(ev, "1001"), RP.rpt_collections(ev), RP.rpt_invoices(ev)]
    html = render.reports_html(reps, "شركة تجربة")
    assert "مندوب أول" in html and "التحصيل" in html


def test_reps_and_commissions_files():
    reps = D.parse_reps([["الكود", "المندوب", "الجنسية", "الراتب الشهري", "التارجت الشهري", "تكاليف أخرى", "يدخل التقييم"],
                         ["1001", "أ", "سعودي", 7000, 100000, 0, 1], ["1002", "ب", "", 3000, 50000, 0, "لا"]])
    assert reps[1]["nationality"] == "مقيم" and reps[1]["active"] == 0
    com = D.parse_commissions([["كود", "المندوب", "2026-01", "2026-02"], ["1001", "أ", 100, None], ["1002", "ب", 50, 70]])
    assert com == {"2026-01": {"1001": 100.0, "1002": 50.0}, "2026-02": {"1002": 70.0}}


def test_screen(db):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from fsapp.ui.reps_view import RepsPage
    app = QApplication.instance() or QApplication([])

    class Win:
        pass
    win = Win()
    win.db, win.ctx = db, None
    page = RepsPage(win)
    page.resize(1400, 900)
    page.load()
    assert page.ev is not None and page.rep.count() == 2
    page.open_report("1002")
    assert page.tabs.currentIndex() == 2
    page.mode.setCurrentIndex(1)
    assert page.months() == [page.end_month()]
    out = os.environ.get("REPS_PREVIEW")
    if out:
        page.mode.setCurrentIndex(0)
        page.show()
        for i, name in ((0, "board"), (2, "rep"), (3, "collections"), (5, "data")):
            page.tabs.setCurrentIndex(i)
            app.processEvents()
            page.grab().save(os.path.join(out, f"{name}.png"))
    app.processEvents()
