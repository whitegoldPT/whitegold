{
    "name": "التحويلات المخزنية بين الفروع والصرف الداخلي (Inter-Branch Transfers & Internal Consumption)",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "طلبات التحويل بين الفروع والمخزن الرئيسي عبر مخزن وسيط ودورة موافقات كاملة",
    "description": """
        تطبيق متكامل لإدارة التحويلات المخزنية بين الفروع ومسارات الصرف الداخلي في أودو 18:
        
        الميزات الرئيسية:
        1. طلب التحويل المخزني من الفرع (Branch Requisition)
        2. دورة الموافقات والاعتمادات (Approval Workflow)
        3. التحويل المرحلي عبر مخزن وسيط (2-Step Transfer via Transit Location):
           - حركة الصرف من المخزن الرئيسي إلى المخزن الوسيط (In Transit)
           - حركة الاستلام في مخزن الفرع من المخزن الوسيط (Done)
        4. تتبع الكميات المطلوبة والمشحونة والمستلمة بدقة
        5. تقرير شحن واستلام قابل للطباعة (PDF Dispatch & Receipt Note)
    """,
    "author": "Ahmed Maher & Antigravity",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "account",
        "stock_account",
        "mrp_account",
        "hr",
        "analytic",
    ],
    "data": [
        "security/consumption_security.xml",
        "security/inter_branch_security.xml",
        "security/ir.model.access.csv",
        "data/sequence_data.xml",
        "data/inter_branch_sequence.xml",
        "data/analytic_data.xml",
        "data/consumption_config_data.xml",
        "views/inter_branch_transfer_views.xml",
        "views/consumption_request_views.xml",
        "views/hr_employee_views.xml",
        "views/res_config_settings_views.xml",
        "views/consumption_forensic_audit_views.xml",
        "views/menu_views.xml",
        "report/inter_branch_transfer_report.xml",
    ],
    "installable": True,
    "application": True,
}
