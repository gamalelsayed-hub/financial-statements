import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fsapp import importer, classifier, engine  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "sample", "sample_trial_balance.xlsx")


def load():
    rows = importer.read_table(SAMPLE)
    first, mapping = importer.guess_mapping(rows)
    accounts = importer.build_accounts(rows, first, mapping)
    parents = importer.mark_parent_accounts(accounts)
    for a in accounts:
        a.category = "exclude" if a.code in parents else classifier.suggest(a.name)
    return accounts, mapping


def test_mapping_detected():
    accounts, mapping = load()
    assert mapping == {"code": 0, "name": 1, "od": 2, "oc": 3, "md": 4, "mc": 5, "cd": 6, "cc": 7}
    assert len(accounts) == 33


def test_all_suggested_and_statements_tie():
    accounts, _ = load()
    missing = [(a.code, a.name) for a in accounts if not a.category]
    assert not missing, missing
    st = engine.build(accounts)
    for k, v in st.checks.items():
        assert abs(v) < 0.01, (k, v)
    assert round(st.is_["net_income"]) == 2632000 - 20000 - 1420000 - 320000 - 96000 - 28000 - 64000 - 95000 - 31000 - 38000
    assert abs(st.cf["cash_close_calc"] - st.cf["cash_close"]) < 0.01


def test_validate_balanced():
    accounts, _ = load()
    leaves = [a for a in accounts if a.category != "exclude"]
    _, problems = importer.validate(leaves)
    assert problems == []


def test_guess_mapping_two_row_header_with_empty_credit_columns():
    """Header: pair names on one row, مدين / دائن on the next; the first accounts (assets) have no credit amounts."""
    rows = [[None, "رقم الحساب", "العملة", "الرصيد الإفتتاحي", "الرصيد الإفتتاحي", "رصيد الحركة", "رصيد الحركة", "الأرصدة", "الأرصدة"],
            ["الرقم", "الاسم", " ", "مدين", "دائن", "مدين", "دائن", "مدين", "دائن"],
            [None] * 9]
    rows += [[1100 + i, f"أصل {i}", "SAR", 1000.0, None, 100.0 if i % 2 else None, None if i % 2 else 50.0,
              1100.0 if i % 2 else 950.0, None] for i in range(45)]
    rows += [[2101, "دائن", "SAR", None, 45000.0, None, 1150.0, None, 46150.0],
             [2102, "حركة", "SAR", None, None, 1100.0, None, 1100.0, None]]
    first, m = importer.guess_mapping(rows)
    assert first == 3
    assert (m["code"], m["name"], m["od"], m["oc"], m["md"], m["mc"], m["cd"], m["cc"]) == (0, 1, 3, 4, 5, 6, 7, 8)
