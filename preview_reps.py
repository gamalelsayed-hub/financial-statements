"""Temporary: screenshots of the reps screen with synthetic data (removed before merging)."""
import os, random, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtWidgets import QApplication
from fsapp.system.db import CompanyDB
from fsapp.ui.reps_view import RepsPage

random.seed(4)
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
db = CompanyDB(os.path.join(out, "demo.fsdb"))
names = ["أحمد سالم", "خالد ناصر", "محمد علي", "سعيد عمر", "ياسر حسن", "فهد صالح", "ماجد عادل", "طارق يوسف"]
reps, items, custs, aging_end, aging_open, rec = [], [], [], [], [], []
for i, n in enumerate(names):
    code = str(5001 + i)
    target = random.choice([200000, 300000, 500000, 900000])
    reps.append({"code": code, "name": n, "nationality": "سعودي" if i < 2 else "مقيم", "salary": random.choice([3000, 4000, 7000]),
                 "target": target, "other": 0, "active": 1, "note": ""})
    vol = target * 10 * random.uniform(0.3, 1.3)
    for k in range(25):
        net = vol / 25 * random.uniform(0.3, 1.7)
        items.append({"rep": code, "rep_name": n, "key": f"01-{k:04d}", "name": f"صنف تجريبي {k}", "net": net,
                      "cost": net * random.uniform(0.62, 0.8)})
    for k in range(12):
        no = f"{code}{k:03d}"
        net = vol / 12 * random.uniform(0.5, 1.5)
        custs.append({"rep": code, "rep_name": n, "key": no, "name": f"مؤسسة تجريبية {i}-{k}", "net": net, "cost": net * 0.72})
        bal = net * random.uniform(0.05, 0.4)
        aging_end.append({"no": no, "name": f"مؤسسة تجريبية {i}-{k}", "rep": f"{code}-{n}", "ctype": "آجل", "b0": bal * 0.6,
                          "b1": bal * 0.2, "b2": bal * 0.2, "b3": 0, "b4": 0})
        rec.append({"vno": str(len(rec)), "date": "2026-10-05", "vtype": "تحويل", "box": "بنك", "acct": "1140101",
                    "acct_name": "", "analytic": no, "amount": net * random.uniform(0.05, 0.15)})
db.save_reps(reps)
db.save_rep_sales("items", "2026-01", "2026-10", items)
db.save_rep_sales("customers", "2026-01", "2026-10", custs)
db.save_aging("customers", "2026-10", aging_end)
db.save_receipts({"2026-10": rec})
db.save_invoices({"2026-10": [{"inv_no": f"26113{i % 3}0{j}", "itype": random.choice(["نقد", "آجل", "من حساب"]),
                               "cust_name": f"مؤسسة تجريبية {i % 8}-{j % 12}", "net": random.uniform(200, 9000)}
                              for i in range(8) for j in range(60)]})
db.save_commissions("2026-10", {r["code"]: random.uniform(500, 6000) for r in reps})
app = QApplication([])

class Win:
    pass
win = Win()
win.db, win.ctx = db, None
page = RepsPage(win)
page.resize(1500, 1000)
page.show()
page.load()
for i, name in ((0, "1_board"), (1, "2_summary"), (2, "3_rep"), (3, "4_collections"), (5, "5_data")):
    page.tabs.setCurrentIndex(i)
    app.processEvents()
    page.grab().save(os.path.join(out, f"{name}.png"))
page.tabs.setCurrentIndex(0)
app.processEvents()
page.board.box.grab().save(os.path.join(out, "6_board_full.png"))
print("ok")
