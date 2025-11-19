from django.urls import path
from . import views

app_name = "digihesabyar"

urlpatterns = [
    # صفحه لندینگ / معرفی
    path("landing/", views.landing, name="landing"),

    # داشبورد و لیست صورتحساب‌ها + آپلود فایل
    path("", views.dashboard, name="dashboard"),

    # جزئیات صورتحساب
    path("invoice/<int:invoice_id>/", views.invoice_detail, name="invoice_detail"),

    # ثبت / ویرایش قیمت خرید DKPCها
    path(
        "invoice/<int:invoice_id>/prices/",
        views.invoice_prices,
        name="invoice_prices",
    ),

    # صفحه پرداخت هزینه پردازش صورتحساب از کیف پول
    path(
        "invoice/<int:invoice_id>/pay/",
        views.invoice_pay,
        name="invoice_pay",
    ),

    # خروجی اکسل سود و زیان برای این صورتحساب
    path(
        "invoice/<int:invoice_id>/export/",
        views.export_invoice_excel,
        name="export_invoice_excel",
    ),

    # کیف پول
    path("wallet/", views.wallet_view, name="wallet"),

    # شارژ کیف پول (تابع درست: wallet_topup_view)
    path("wallet/topup/", views.wallet_topup_view, name="wallet_topup"),

    # ماشین‌حساب رایگان
    path("calculator/", views.calculator, name="calculator"),
]
