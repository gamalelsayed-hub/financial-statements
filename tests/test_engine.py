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
