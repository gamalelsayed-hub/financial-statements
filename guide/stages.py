STAGES = [
    {"id": "s0", "title": "التجهيز", "files": [],
     "intro": ("الخطوات بالتفصيل مع الرسومات في قسم «ابدأ من هنا» فوق. باختصار: بايثون 3.10 أو أحدث، و VS Code مع إضافة Python، ومجلد للمشروع فيه "
               "المجلدات fsapp و fsapp/system و fsapp/ui، وفي كل واحد منها ملف فاضي اسمه __init__.py. بعدها من شاشة الأوامر في VS Code ثبّت المكتبات الأربع:"),
     "code": "pip install PySide6==6.12.0 openpyxl==3.1.5 pdfplumber==0.11.10 certifi==2024.8.30",
     "check": "اكتب python -c \"import PySide6, openpyxl, pdfplumber\" ولو ما طلع خطأ فالتجهيز تمام."},
    {"id": "s1", "title": "المرحلة 1: ملف الشركة وقاعدة البيانات",
     "files": ["fsapp/version.py", "fsapp/system/defaults.py", "fsapp/system/db.py"],
     "intro": "تبدأ بالبيانات: وين تنحفظ وكيف تنقرأ. ما فيه شاشات ولا حسابات بعد.",
     "check": ("في سطر أوامر بايثون (اكتب python): from fsapp.system.db import CompanyDB ثم db = CompanyDB('test.fsdb') ثم "
               "db.list_names('fs_items')[:5] — لازم تطلع أول 5 بنود. وجرب db.save_tb('2026-01', [('1101', 'صندوق', 0, 0, 100, 0, 100, 0)]) ثم db.tb('2026-01').")},
    {"id": "s2", "title": "المرحلة 2: قراءة ميزان المراجعة من ملف",
     "files": ["fsapp/importer.py"],
     "intro": "تحويل ملف Excel أو CSV من النظام المحاسبي إلى حسابات مرتبة.",
     "check": ("rows = read_table('ميزان.xlsx') ثم first, m = guess_mapping(rows) ثم accs = build_accounts(rows, first, m) ثم "
               "validate(accs) — لازم يطلع مجموع الأعمدة الستة وأي عدم توازن. بعدها احفظه في القاعدة بـ db.save_tb.")},
    {"id": "s3", "title": "المرحلة 3: محرك الحسابات",
     "files": ["fsapp/system/calc.py"],
     "intro": "أهم مرحلة: الأرصدة، قائمة الدخل، المركز المالي، التدفقات، الفروع، النسب. خذ وقتك فيها، وقارن النتائج مع الإكسيل حقك.",
     "check": ("ارفع ميزانين (شهرين ورا بعض) بالمرحلة 2، اربط كم حساب في جدول accounts ببنود (db.save_accounts)، ثم: "
               "from fsapp.system.calc import Ctx ثم ctx = Ctx(db) ثم ctx.is_figures(['2026-02'])['ni'] و ctx.bs_figures(['2026-02'], 2)['diff'] (لازم صفر لو كل الحسابات مربوطة).")},
    {"id": "s4", "title": "المرحلة 4: التقارير والفحوصات وعرضها",
     "files": ["fsapp/system/blocks.py", "fsapp/system/aging.py", "fsapp/categories.py", "fsapp/classifier.py",
               "fsapp/system/diagnose.py", "fsapp/system/reports.py", "fsapp/system/render.py", "fsapp/system/dashboard.py"],
     "intro": ("شكل التقرير، ثم كل التقارير، ثم تحويلها لـ HTML و Excel. categories و classifier من وضع التحليل السريع لكن التشخيص يحتاجهم لاقتراح الربط بالاسم، فتكتبهم هنا. "
               "تنبيه: في آخر reports.py علّق سطري الاستيراد من annual و item_reports واحذفهم من ALL_REPORTS و REPORT_GROUPS مؤقتًا، وترجعهم في المرحلتين 5 و 6."),
     "check": ("from fsapp.system import reports as R, render ثم rep = R.build('is', ctx, R.Params(end='2026-02')) ثم "
               "open('is.html', 'w', encoding='utf-8').write(render.report_html(rep, 'شركتي')) وافتح الملف في المتصفح. وجرب render.write_excel([rep], 'شركتي', 'is.xlsx').")},
    {"id": "s5", "title": "المرحلة 5: مسودة القوائم والمقارنات السنوية",
     "files": ["fsapp/system/draft.py", "fsapp/system/draft_export.py", "fsapp/system/annual.py"],
     "intro": "القوائم بشكلها المنشور مع الإيضاحات، والمقارنات بين السنوات. بعد annual.py رجّع سطر استيراده في reports.py.",
     "check": ("from fsapp.system import draft as DR, draft_export as DX ثم dr = DR.build(ctx, '2026-02') ثم DR.bs_totals(dr.cur.bs)['diff'] (صفر) ثم "
               "DX.to_excel(dr, ctx, 'draft.xlsx', {}).")},
    {"id": "s6", "title": "المرحلة 6: الأصناف ومبيعاتها ومشترياتها",
     "files": ["fsapp/system/items.py", "fsapp/system/item_reports.py"],
     "intro": "قراءة ملفات الأصناف والمبيعات والمشتريات (Excel و PDF) وتقاريرها. بعد item_reports.py رجّع سطر استيراده في reports.py.",
     "check": "from fsapp.system import items as I ثم span, rows, check = I.parse_sales_pdf('مبيعات.pdf') ثم len(rows) و check['grand'].",},
    {"id": "s7", "title": "المرحلة 7: الاستيراد من نموذج الإكسيل القديم (اختياري)",
     "files": ["fsapp/system/migrate.py"],
     "intro": "تحتاجه بس لو بتنقل شركة من نموذج الإكسيل القديم. تقدر تأجله.",
     "check": "from fsapp.system import migrate ثم migrate.migrate('النموذج.xlsx', CompanyDB('new.fsdb')) — يطبع ملخص كل جزء انستورد."},
    {"id": "s8", "title": "المرحلة 8: الشاشات وتشغيل البرنامج",
     "files": ["fsapp/ui/zoom.py", "fsapp/ui/progress.py", "fsapp/ui/table_tools.py", "fsapp/i18n.py",
               "fsapp/ui/aging_view.py", "fsapp/ui/dashboard_view.py", "fsapp/ui/items_view.py", "fsapp/ui/draft_dialog.py",
               "fsapp/updater.py", "fsapp/ui/system_window.py", "main.py"],
     "intro": ("الأدوات الصغيرة أول (الزوم، العداد، تثبيت العمود)، ثم الصفحات، ثم النافذة الرئيسية، وآخر شي main.py. "
               "i18n.py من وضع التحليل السريع لكن main.py يستورده، فتكتبه هنا. "
               "زر «تحليل سريع لميزان واحد» في شاشة البداية يشتغل بعد المرحلة 9."),
     "check": "python main.py — تطلع شاشة البداية. سوّ شركة جديدة، ارفع ميزان من «البيانات الشهرية»، اربط الحسابات، وافتح التقارير."},
    {"id": "s9", "title": "المرحلة 9: وضع التحليل السريع لميزان واحد",
     "files": ["fsapp/engine.py", "fsapp/reports.py", "fsapp/export_excel.py", "fsapp/ui/main_window.py"],
     "intro": "وضع مستقل يحلل ميزان واحد بدون ملف شركة: رفع، تصنيف، قوائم، نسب. يحتاج مجلد sample فيه نموذج الميزان الفاضي (لزر «تنزيل نموذج»).",
     "check": "من شاشة البداية اضغط «تحليل سريع لميزان واحد» وارفع ميزان."},
]
