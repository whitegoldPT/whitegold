# POS Customer Create Access Rights (Odoo 18)

تقييد الصلاحيات لإنشاء عملاء جدد من شاشة نقاط البيع.

## المميزات

- مجموعة صلاحيات جديدة: **POS / Create Customer**
- المستخدمون خارج هذه المجموعة لا يستطيعون إنشاء عملاء جدد من POS
- حماية على الواجهة: الضغط على زرار "Create" يظهر رسالة Access Denied
- حماية على السيرفر: `res.partner.create()` يرفض المحاولات اللي بتيجي من POS context
- مدير POS يحصل على الصلاحية تلقائياً (implied_ids)

## فلسفة التصميم

النسخة دي بتعمل **RPC call واحدة بسيطة** عشان تتأكد من صلاحية المستخدم — مفيش أي تدخل في POS data loaders أو `_load_pos_data_fields`. ده بيمنع أخطاء زي `is_posbox` اللي بتظهر مع الموديولات اللي بتعدل في loader chain.

## التغييرات في أودوو 18

- اسم الكلاس بقى `PartnerList` بدل `PartnerListScreen`
- خدمة الـ Popup اتبدلت بـ `Dialog` service (`AlertDialog` بدل `ErrorPopup`)
- المسار `@web/core/confirmation_dialog/confirmation_dialog` للـ AlertDialog
- الباقي زي ما هو من ناحية الباك إند

## التثبيت

1. انسخ مجلد `pos_customer_create_access` في addons path
2. شغل أودوو من جديد
3. حدّث قائمة التطبيقات وثبّت **POS Customer Create Access Rights**
4. اعمل hard refresh (Ctrl+Shift+R) لشاشة POS أول مرة

## الإعداد

### إضافة مستخدمين للمجموعة الجديدة
- Settings → Users & Companies → Users
- افتح المستخدم
- في تبويب *Other* (لازم Developer Mode)، فعّل **POS / Create Customer**
- مدير POS عنده الصلاحية تلقائياً

## السلوك

- زرار "Create" بيفضل ظاهر في قائمة العملاء في POS
- لو المستخدم مش معاه صلاحية، الضغط بيظهر AlertDialog "Access Denied"
- حفظ عميل جديد بيتمنع برضو على مستوى الـ JS (defense-in-depth)
- على السيرفر: أي محاولة إنشاء partner من سياق POS بتترفض بـ `AccessError`
- البحث واختيار العملاء الموجودين شغّال عادي — التقييد بس على الإنشاء

## ملفات الموديول

```
pos_customer_create_access/
├── __init__.py
├── __manifest__.py
├── README.md
├── models/
│   ├── __init__.py
│   └── res_partner.py        # ResUsers + ResPartner
├── security/
│   ├── ir.model.access.csv
│   └── pos_security_groups.xml
└── static/src/js/
    └── partner_list.js
```

## ملاحظات

- لو فيه موديول POS تاني بيعمل override للـ PartnerList، تأكد إنه متحمل قبل الموديول ده (بترتيب الـ depends).
- لو الـ AlertDialog مظهرش لأي سبب، الكود بيـ fallback لـ `alert()` العادي.
- حماية السيرفر بتشتغل دايماً حتى لو حماية الـ JS اتعطلت لأي سبب.

## Author

Ahmed
