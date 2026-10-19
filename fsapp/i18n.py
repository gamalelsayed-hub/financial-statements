"""Arabic / English texts."""
from .categories import BY_KEY

_LANG = {"value": "ar"}


def set_lang(lang):
    _LANG["value"] = lang


def lang():
    return _LANG["value"]


def t(key, **kw):
    pair = TEXTS.get(key)
    if pair is None:
        if key in BY_KEY:
            c = BY_KEY[key]
            s = c.ar if lang() == "ar" else c.en
        elif key.startswith("cf_") and key[3:] in BY_KEY:
            s = cf_label(key[3:])
        else:
            s = key
    else:
        s = pair[0] if lang() == "ar" else pair[1]
    return s.format(**kw) if kw else s


def cf_label(cat):
    pair = CF_LABELS.get(cat)
    if pair:
        return pair[0] if lang() == "ar" else pair[1]
    c = BY_KEY[cat]
    return (f"التغير في {c.ar}" if lang() == "ar" else f"Change in {c.en.lower()}")


CF_LABELS = {
    "accum_dep": ("الإهلاك والاستهلاك (التغير في مجمع الإهلاك)", "Depreciation & amortization (change in accumulated depreciation)"),
    "provisions": ("التغير في المخصصات والالتزامات طويلة الأجل", "Change in provisions and long-term liabilities"),
    "receivables": ("(الزيادة) النقص في العملاء وأوراق القبض", "(Increase) decrease in trade receivables"),
    "inventory": ("(الزيادة) النقص في المخزون", "(Increase) decrease in inventory"),
    "prepaid": ("(الزيادة) النقص في المصروفات المقدمة والأرصدة المدينة", "(Increase) decrease in prepayments and other receivables"),
    "payables": ("الزيادة (النقص) في الموردين وأوراق الدفع", "Increase (decrease) in trade payables"),
    "accrued": ("الزيادة (النقص) في المستحقات والأرصدة الدائنة", "Increase (decrease) in accruals and other payables"),
    "tax_payable": ("الزيادة (النقص) في الضرائب المستحقة", "Increase (decrease) in taxes payable"),
    "st_investments": ("(شراء) بيع استثمارات قصيرة الأجل", "(Purchase) sale of short-term investments"),
    "ppe": ("(شراء) بيع أصول ثابتة", "(Purchase) disposal of property, plant and equipment"),
    "cwip": ("مدفوعات مشروعات تحت التنفيذ", "Payments for capital work in progress"),
    "intangibles": ("(شراء) بيع أصول غير ملموسة", "(Purchase) disposal of intangible assets"),
    "lt_investments": ("(شراء) بيع استثمارات طويلة الأجل", "(Purchase) sale of long-term investments"),
    "other_nca": ("التغير في الأصول غير المتداولة الأخرى", "Change in other non-current assets"),
    "st_loans": ("المحصل (المسدد) من البنوك والقروض قصيرة الأجل", "Proceeds from (repayment of) short-term borrowings"),
    "current_ltd": ("التغير في أقساط القروض المستحقة خلال العام", "Change in current portion of long-term loans"),
    "lt_loans": ("المحصل (المسدد) من القروض طويلة الأجل", "Proceeds from (repayment of) long-term loans"),
    "capital": ("الزيادة (التخفيض) في رأس المال", "Capital contributed (withdrawn)"),
    "reserves": ("التغير في الاحتياطيات", "Change in reserves"),
    "retained_earnings": ("توزيعات وتسويات على الأرباح المرحلة", "Dividends and adjustments to retained earnings"),
    "drawings": ("توزيعات أرباح / مسحوبات الشركاء", "Dividends paid / partners' drawings"),
}

TEXTS = {
    # app / ui
    "app_title": ("القوائم المالية من ميزان المراجعة", "Financial Statements from Trial Balance"),
    "step_import": ("١. رفع ميزان المراجعة", "1. Upload trial balance"),
    "step_classify": ("٢. تصنيف الحسابات", "2. Classify accounts"),
    "step_statements": ("٣. القوائم المالية", "3. Financial statements"),
    "step_analysis": ("٤. التحليل المالي", "4. Financial analysis"),
    "language": ("English", "عربي"),
    "export_excel": ("تصدير Excel", "Export Excel"),
    "export_pdf": ("تصدير PDF", "Export PDF"),
    "company": ("اسم الشركة:", "Company name:"),
    "period": ("الفترة المنتهية في:", "Period ended:"),
    "months": ("عدد شهور الفترة:", "Months in period:"),
    "currency": ("العملة:", "Currency:"),
    "choose_file": ("اختيار ملف ميزان المراجعة (Excel / CSV)...", "Choose trial balance file (Excel / CSV)..."),
    "download_template": ("حفظ نموذج ميزان فارغ", "Save blank template"),
    "load_sample": ("تجربة بميزان نموذجي", "Try a sample trial balance"),
    "import_help": (
        "ارفع ميزان المراجعة بالشكل المعتاد: كود الحساب، اسم الحساب، ثم ٦ أعمدة: "
        "رصيد أول المدة (مدين / دائن)، الحركة (مدين / دائن)، رصيد آخر المدة (مدين / دائن). "
        "البرنامج سيحاول التعرف على الأعمدة تلقائيًا وتقدر تعدّلها.",
        "Upload the trial balance in the usual layout: account code, account name, then 6 columns: "
        "opening (Dr / Cr), movement (Dr / Cr), closing (Dr / Cr). "
        "The app detects the columns automatically and you can adjust them."),
    "no_file": ("لم يتم اختيار ملف بعد", "No file selected yet"),
    "loaded_summary": ("تم تحميل {n} حساب من: {f}", "Loaded {n} accounts from: {f}"),
    "next_classify": ("التالي: تصنيف الحسابات ←", "Next: classify accounts →"),
    "totals": ("الإجماليات", "Totals"),
    "debit": ("مدين", "Debit"),
    "credit": ("دائن", "Credit"),
    "opening": ("أول المدة", "Opening"),
    "movement": ("الحركة", "Movement"),
    "closing": ("آخر المدة", "Closing"),
    "balanced": ("متوازن ✓", "Balanced ✓"),
    "difference": ("فرق: {d}", "Difference: {d}"),
    "row_problems": ("حسابات رصيدها الختامي لا يساوي الافتتاحي + الحركة: {n}", "Accounts where closing ≠ opening + movement: {n}"),
    "parents_excluded": ("تم استبعاد {n} حساب رئيسي (إجمالي لحسابات فرعية) تلقائيًا. راجعها في شاشة التصنيف.",
                         "{n} parent (summary) accounts were excluded automatically. Review them on the classification screen."),
    "map_title": ("تحديد أعمدة ميزان المراجعة", "Map trial balance columns"),
    "map_help": ("حدد العمود المقابل لكل بيان. أول صف بيانات هو أول صف فيه حساب (بعد العناوين).",
                 "Select the column for each field. First data row is the first row containing an account (after headers)."),
    "first_row": ("أول صف بيانات:", "First data row:"),
    "role_code": ("كود الحساب", "Account code"),
    "role_name": ("اسم الحساب", "Account name"),
    "role_od": ("أول المدة - مدين", "Opening - Debit"),
    "role_oc": ("أول المدة - دائن", "Opening - Credit"),
    "role_md": ("الحركة - مدين", "Movement - Debit"),
    "role_mc": ("الحركة - دائن", "Movement - Credit"),
    "role_cd": ("آخر المدة - مدين", "Closing - Debit"),
    "role_cc": ("آخر المدة - دائن", "Closing - Credit"),
    "not_available": ("— غير موجود —", "— not available —"),
    "column": ("عمود", "Column"),
    "ok": ("موافق", "OK"),
    "cancel": ("إلغاء", "Cancel"),
    "need_name_amounts": ("لازم تحدد عمود اسم الحساب، وعلى الأقل رصيد آخر المدة (أو أول المدة + الحركة).",
                          "Select the account name column and at least the closing balance (or opening + movement)."),
    "classify_help": ("حدد نوع كل حساب. البرنامج اقترح تصنيفًا مبدئيًا لكل حساب من اسمه — راجعه وعدّله. "
                      "تقدر تحدد أكثر من صف وتطبق عليهم تصنيف واحد.",
                      "Choose the type of each account. The app pre-filled a suggestion from each account name — review and adjust. "
                      "You can select several rows and apply one category to all of them."),
    "search": ("بحث بالاسم أو الكود...", "Search by name or code..."),
    "only_unclassified": ("غير المصنف فقط", "Unclassified only"),
    "apply_selected": ("تطبيق على المحدد", "Apply to selected"),
    "auto_suggest": ("اقتراح تلقائي لغير المصنف", "Auto-suggest unclassified"),
    "save_mapping": ("حفظ التصنيف في ملف", "Save classification to file"),
    "load_mapping": ("تحميل تصنيف من ملف", "Load classification from file"),
    "confirm_generate": ("تأكيد وإنشاء القوائم المالية ✓", "Confirm and generate statements ✓"),
    "col_code": ("الكود", "Code"),
    "col_name": ("اسم الحساب", "Account name"),
    "col_closing": ("الرصيد الختامي", "Closing balance"),
    "col_movement": ("صافي الحركة", "Net movement"),
    "col_category": ("التصنيف", "Category"),
    "unclassified": ("— اختر التصنيف —", "— choose category —"),
    "classified_count": ("مصنف: {a} من {b}", "Classified: {a} of {b}"),
    "unclassified_left": ("يوجد {n} حساب بدون تصنيف. صنفها أو اختر «مستبعد» قبل المتابعة.",
                          "{n} accounts are not classified. Classify them or mark them as excluded first."),
    "dr": ("مدين", "Dr"),
    "cr": ("دائن", "Cr"),
    "mapping_applied": ("تم تطبيق التصنيف على {n} حساب", "Classification applied to {n} accounts"),
    "memory_applied": ("تم استرجاع تصنيفاتك السابقة لـ {n} حساب", "Restored your previous classification for {n} accounts"),
    "exported": ("تم الحفظ في:\n{p}", "Saved to:\n{p}"),
    "generate_first": ("أنشئ القوائم المالية أولًا.", "Generate the statements first."),
    "error": ("خطأ", "Error"),
    "read_error": ("تعذر قراءة الملف:\n{e}", "Could not read the file:\n{e}"),
    "warning": ("تنبيه", "Warning"),
    "info": ("معلومة", "Information"),
    "no_data_rows": ("لم يتم العثور على حسابات في الملف بالأعمدة المحددة.", "No accounts found with the selected columns."),
    "tab_bs": ("قائمة المركز المالي", "Balance sheet"),
    "tab_is": ("قائمة الدخل", "Income statement"),
    "tab_cf": ("قائمة التدفقات النقدية", "Cash flow statement"),
    "tab_eq": ("قائمة التغير في حقوق الملكية", "Changes in equity"),
    "tab_notes": ("الإيضاحات (تفاصيل البنود)", "Notes (line details)"),
    "tab_checks": ("مراجعة التوازن", "Integrity checks"),

    # statement lines
    "statement_of_fp": ("قائمة المركز المالي", "Statement of Financial Position"),
    "statement_of_pl": ("قائمة الدخل", "Income Statement"),
    "statement_of_cf": ("قائمة التدفقات النقدية (الطريقة غير المباشرة)", "Statement of Cash Flows (indirect method)"),
    "statement_of_eq": ("قائمة التغير في حقوق الملكية", "Statement of Changes in Equity"),
    "notes_title": ("الإيضاحات المتممة — تفاصيل البنود", "Notes — line item details"),
    "ratios_title": ("التحليل المالي والمؤشرات", "Financial Analysis and Ratios"),
    "as_at": ("في {d}", "As at {d}"),
    "for_period": ("عن الفترة المنتهية في {d}", "For the period ended {d}"),
    "current": ("آخر المدة", "Closing"),
    "prior": ("أول المدة", "Opening"),
    "amount": ("المبلغ", "Amount"),
    "note": ("إيضاح", "Note"),
    "assets": ("الأصول", "Assets"),
    "total_CA": ("إجمالي الأصول المتداولة", "Total current assets"),
    "total_NCA": ("إجمالي الأصول غير المتداولة", "Total non-current assets"),
    "total_assets": ("إجمالي الأصول", "Total assets"),
    "liab_equity": ("الالتزامات وحقوق الملكية", "Liabilities and equity"),
    "total_CL": ("إجمالي الالتزامات المتداولة", "Total current liabilities"),
    "total_NCL": ("إجمالي الالتزامات غير المتداولة", "Total non-current liabilities"),
    "total_liabilities": ("إجمالي الالتزامات", "Total liabilities"),
    "total_EQ": ("إجمالي حقوق الملكية", "Total equity"),
    "total_le": ("إجمالي الالتزامات وحقوق الملكية", "Total liabilities and equity"),
    "net_income_period": ("صافي ربح (خسارة) الفترة", "Net profit (loss) for the period"),
    "gross_profit": ("مجمل الربح", "Gross profit"),
    "operating_profit": ("ربح التشغيل", "Operating profit"),
    "profit_before_tax": ("صافي الربح قبل الضريبة", "Profit before tax"),
    "net_income": ("صافي ربح (خسارة) الفترة", "Net profit (loss) for the period"),
    "cfo_title": ("التدفقات النقدية من الأنشطة التشغيلية", "Cash flows from operating activities"),
    "cfi_title": ("التدفقات النقدية من الأنشطة الاستثمارية", "Cash flows from investing activities"),
    "cff_title": ("التدفقات النقدية من الأنشطة التمويلية", "Cash flows from financing activities"),
    "adjustments": ("تسويات لبنود غير نقدية:", "Adjustments for non-cash items:"),
    "wc_changes": ("التغير في رأس المال العامل:", "Changes in working capital:"),
    "cfo": ("صافي النقدية من الأنشطة التشغيلية", "Net cash from operating activities"),
    "cfi": ("صافي النقدية من الأنشطة الاستثمارية", "Net cash from investing activities"),
    "cff": ("صافي النقدية من الأنشطة التمويلية", "Net cash from financing activities"),
    "net_change": ("صافي التغير في النقدية", "Net change in cash"),
    "cash_open": ("النقدية أول الفترة", "Cash at beginning of period"),
    "cash_close": ("النقدية آخر الفترة", "Cash at end of period"),
    "eq_open": ("الرصيد أول الفترة", "Opening balance"),
    "eq_ni": ("صافي ربح (خسارة) الفترة", "Net profit (loss) for the period"),
    "eq_other": ("حركات أخرى (زيادة رأس مال، توزيعات، تحويلات)", "Other movements (capital, dividends, transfers)"),
    "eq_close": ("الرصيد آخر الفترة", "Closing balance"),
    "total": ("الإجمالي", "Total"),
    "check_bs": ("توازن قائمة المركز المالي (آخر المدة)", "Balance sheet balances (closing)"),
    "check_bs_prior": ("توازن قائمة المركز المالي (أول المدة)", "Balance sheet balances (opening)"),
    "check_ni": ("صافي الربح = صافي حركة حسابات النتيجة", "Net profit = net movement of P&L accounts"),
    "check_cash": ("النقدية المحسوبة من التدفقات = رصيد النقدية الفعلي", "Cash per cash flow = actual cash balance"),
    "check_ok": ("✓ سليم", "✓ OK"),
    "check_fail": ("✗ فرق {d}", "✗ difference {d}"),
    "checks_hint": ("لو في فرق، غالبًا السبب: ميزان المراجعة نفسه غير متوازن، أو حساب رئيسي لم يُستبعد فتكرر، أو حساب غير مصنف.",
                    "If there is a difference, usually: the trial balance itself is unbalanced, a parent account was not excluded, or an account is unclassified."),

    # ratio groups
    "grp_liquidity": ("مؤشرات السيولة", "Liquidity ratios"),
    "grp_profitability": ("مؤشرات الربحية", "Profitability ratios"),
    "grp_activity": ("مؤشرات النشاط والكفاءة التشغيلية", "Activity / operating efficiency ratios"),
    "grp_leverage": ("مؤشرات الرفع المالي والتمويل", "Leverage / financing ratios"),
    "grp_cashflow": ("مؤشرات التدفقات النقدية", "Cash flow ratios"),
    "ratio": ("المؤشر", "Ratio"),
    "value": ("القيمة", "Value"),
    "formula": ("طريقة الحساب", "Formula"),
    "assessment": ("التقييم", "Assessment"),
    "meaning": ("المعنى", "Meaning"),
    "st_good": ("جيد", "Good"),
    "st_warn": ("يحتاج متابعة", "Watch"),
    "st_bad": ("ضعيف", "Weak"),
    "st_info": ("للعلم", "Info"),
    "st_na": ("غير متاح", "N/A"),
    "times": ("مرة", "x"),
    "days_unit": ("يوم", "days"),
    "summary": ("ملخص التحليل", "Analysis summary"),
    "ratios_note": ("ملاحظة: معدلات الدوران تُحسب على متوسط رصيد أول وآخر المدة، وحدود التقييم إرشادية عامة وتختلف حسب النشاط.",
                    "Note: turnover ratios use the average of opening and closing balances; assessment thresholds are general guidance and vary by industry."),
    "key_figures": ("أرقام رئيسية", "Key figures"),
    "sheet_classification": ("تصنيف الحسابات", "Account classification"),
    "group": ("المجموعة", "Group"),
}

RATIO_TEXT = {
    "current_ratio": (("نسبة التداول", "Current ratio"), ("الأصول المتداولة ÷ الالتزامات المتداولة", "Current assets ÷ current liabilities"),
                      ("قدرة الشركة على سداد التزاماتها قصيرة الأجل من أصولها المتداولة.", "Ability to pay short-term obligations from current assets.")),
    "quick_ratio": (("نسبة السيولة السريعة", "Quick ratio"), ("(النقدية + الاستثمارات قصيرة الأجل + العملاء) ÷ الالتزامات المتداولة", "(Cash + short-term investments + receivables) ÷ current liabilities"),
                    ("السيولة بدون الاعتماد على بيع المخزون.", "Liquidity without relying on selling inventory.")),
    "cash_ratio": (("نسبة النقدية", "Cash ratio"), ("(النقدية + الاستثمارات قصيرة الأجل) ÷ الالتزامات المتداولة", "(Cash + short-term investments) ÷ current liabilities"),
                   ("الجزء من الالتزامات المتداولة الممكن سداده فورًا.", "Share of current liabilities payable immediately.")),
    "working_capital": (("رأس المال العامل", "Working capital"), ("الأصول المتداولة − الالتزامات المتداولة", "Current assets − current liabilities"),
                        ("هامش الأمان لتمويل النشاط اليومي.", "Cushion financing day-to-day operations.")),
    "gross_margin": (("هامش مجمل الربح", "Gross margin"), ("مجمل الربح ÷ المبيعات", "Gross profit ÷ revenue"),
                     ("كفاءة التسعير والتحكم في تكلفة المبيعات.", "Pricing power and cost of sales control.")),
    "operating_margin": (("هامش ربح التشغيل", "Operating margin"), ("ربح التشغيل ÷ المبيعات", "Operating profit ÷ revenue"),
                         ("ربحية النشاط الأساسي بعد المصروفات التشغيلية.", "Core business profitability after operating expenses.")),
    "ebitda_margin": (("هامش EBITDA", "EBITDA margin"), ("(ربح التشغيل + الإهلاك) ÷ المبيعات", "(Operating profit + depreciation) ÷ revenue"),
                      ("الربح التشغيلي قبل الإهلاك — مؤشر للتدفق النقدي التشغيلي.", "Operating profit before depreciation — a proxy for operating cash generation.")),
    "net_margin": (("هامش صافي الربح", "Net margin"), ("صافي الربح ÷ المبيعات", "Net profit ÷ revenue"),
                   ("ما يتبقى من كل جنيه مبيعات كربح صافي.", "What remains from each unit of revenue as net profit.")),
    "roa": (("العائد على الأصول ROA", "Return on assets (ROA)"), ("صافي الربح ÷ متوسط إجمالي الأصول", "Net profit ÷ average total assets"),
            ("كفاءة استخدام الأصول في تحقيق الربح.", "How efficiently assets generate profit.")),
    "roe": (("العائد على حقوق الملكية ROE", "Return on equity (ROE)"), ("صافي الربح ÷ متوسط حقوق الملكية", "Net profit ÷ average equity"),
            ("العائد المحقق على أموال الملاك.", "Return generated on owners' funds.")),
    "asset_turnover": (("معدل دوران الأصول", "Asset turnover"), ("المبيعات ÷ متوسط إجمالي الأصول", "Revenue ÷ average total assets"),
                       ("حجم المبيعات المتولد من كل جنيه أصول.", "Revenue generated per unit of assets.")),
    "receivables_turnover": (("معدل دوران العملاء", "Receivables turnover"), ("المبيعات ÷ متوسط العملاء", "Revenue ÷ average receivables"),
                             ("سرعة تحصيل المبيعات الآجلة.", "How quickly credit sales are collected.")),
    "dso": (("متوسط فترة التحصيل", "Days sales outstanding (DSO)"), ("أيام الفترة ÷ معدل دوران العملاء", "Days in period ÷ receivables turnover"),
            ("عدد الأيام في المتوسط لتحصيل مستحقات العملاء.", "Average days to collect from customers.")),
    "inventory_turnover": (("معدل دوران المخزون", "Inventory turnover"), ("تكلفة المبيعات ÷ متوسط المخزون", "Cost of sales ÷ average inventory"),
                           ("عدد مرات بيع وتجديد المخزون خلال الفترة.", "Times inventory is sold and replaced in the period.")),
    "dio": (("متوسط فترة التخزين", "Days inventory outstanding (DIO)"), ("أيام الفترة ÷ معدل دوران المخزون", "Days in period ÷ inventory turnover"),
            ("عدد الأيام التي يبقاها المخزون قبل البيع.", "Average days inventory is held before sale.")),
    "payables_turnover": (("معدل دوران الموردين", "Payables turnover"), ("تكلفة المبيعات ÷ متوسط الموردين", "Cost of sales ÷ average payables"),
                          ("سرعة سداد مستحقات الموردين.", "How quickly suppliers are paid.")),
    "dpo": (("متوسط فترة السداد للموردين", "Days payables outstanding (DPO)"), ("أيام الفترة ÷ معدل دوران الموردين", "Days in period ÷ payables turnover"),
            ("عدد الأيام في المتوسط لسداد الموردين.", "Average days taken to pay suppliers.")),
    "ccc": (("دورة التحويل النقدي", "Cash conversion cycle"), ("فترة التحصيل + فترة التخزين − فترة السداد", "DSO + DIO − DPO"),
            ("عدد الأيام بين دفع النقدية للموردين وتحصيلها من العملاء.", "Days between paying suppliers and collecting from customers.")),
    "debt_to_equity": (("إجمالي الالتزامات إلى حقوق الملكية", "Total liabilities to equity"), ("إجمالي الالتزامات ÷ حقوق الملكية", "Total liabilities ÷ equity"),
                       ("مدى اعتماد الشركة على أموال الغير مقارنة بأموال الملاك.", "Reliance on outside funds versus owners' funds.")),
    "debt_ratio": (("نسبة المديونية", "Debt ratio"), ("إجمالي الالتزامات ÷ إجمالي الأصول", "Total liabilities ÷ total assets"),
                   ("نسبة الأصول الممولة بالالتزامات.", "Share of assets financed by liabilities.")),
    "equity_ratio": (("نسبة الملكية", "Equity ratio"), ("حقوق الملكية ÷ إجمالي الأصول", "Equity ÷ total assets"),
                     ("نسبة الأصول الممولة من الملاك.", "Share of assets financed by owners.")),
    "financial_debt_to_equity": (("القروض إلى حقوق الملكية", "Borrowings to equity"), ("(البنوك والقروض) ÷ حقوق الملكية", "(Bank debt and loans) ÷ equity"),
                                 ("الرفع المالي من الديون التي تحمل فوائد.", "Leverage from interest-bearing debt.")),
    "interest_coverage": (("معدل تغطية الفوائد", "Interest coverage"), ("ربح التشغيل ÷ المصروفات التمويلية", "Operating profit ÷ finance costs"),
                          ("عدد مرات تغطية الأرباح التشغيلية لتكلفة الاقتراض.", "Times operating profit covers interest.")),
    "ocf_ratio": (("نسبة التدفق النقدي التشغيلي", "Operating cash flow ratio"), ("صافي النقدية من التشغيل ÷ الالتزامات المتداولة", "Operating cash flow ÷ current liabilities"),
                  ("قدرة النقدية المتولدة من التشغيل على سداد الالتزامات قصيرة الأجل.", "Ability of operating cash flow to cover current liabilities.")),
    "cash_quality": (("جودة الأرباح (النقدية ÷ الربح)", "Earnings quality (cash ÷ profit)"), ("صافي النقدية من التشغيل ÷ صافي الربح", "Operating cash flow ÷ net profit"),
                     ("مدى تحول الأرباح المحاسبية إلى نقدية فعلية.", "How much of accounting profit turns into cash.")),
    "free_cash_flow": (("التدفق النقدي الحر", "Free cash flow"), ("صافي النقدية من التشغيل − الإنفاق الرأسمالي", "Operating cash flow − capital expenditure"),
                       ("النقدية المتاحة بعد الاستثمار في الأصول للتوزيع أو سداد الديون.", "Cash left after capex for dividends or debt repayment.")),
    "cash_debt_coverage": (("تغطية النقدية للالتزامات", "Cash flow to total liabilities"), ("صافي النقدية من التشغيل ÷ إجمالي الالتزامات", "Operating cash flow ÷ total liabilities"),
                           ("قدرة التشغيل على سداد إجمالي الالتزامات.", "Ability of operations to repay total liabilities.")),
}


def ratio_text(key, part):
    """part: 0 name, 1 formula, 2 meaning"""
    pair = RATIO_TEXT[key][part]
    return pair[0] if lang() == "ar" else pair[1]
