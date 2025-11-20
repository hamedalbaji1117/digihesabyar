from __future__ import annotations

from io import BytesIO

import pandas as pd

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import (
    InvoiceFile,
    InvoiceRow,
    ProductPrice,
    Wallet,
    WalletTransaction,
    PricingTier,
    Coupon,
)
from .services import process_invoice_file, normalize_number
from .forms import InvoiceUploadForm


# ----------------------------------------------------------------------
#  توابع کمکی
# ----------------------------------------------------------------------


def _get_or_create_wallet(user) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(user=user, defaults={"balance": 0})
    return wallet


def recalc_profit(invoice: InvoiceFile):
    """
    برای تمام ردیف‌های این صورتحساب، سود/زیان و مالیات را دوباره محاسبه می‌کند.
    - برای مرجوعی‌ها همیشه profit = 0
    - برای ردیف‌هایی که purchase_price <= 0 باشد هم profit = 0
    - فرمول مالیات: 10٪ از (کمیسیون + هزینه پردازش)
    - فرمول هزینه کل:
        * نقدی:   خرید + کمیسیون + ارسال + پردازش + مالیات
        * اعتباری: خرید + درآمد توسعه پلتفرم + کمیسیون + ارسال + پردازش + مالیات
    """
    rows = InvoiceRow.objects.filter(invoice=invoice)
    update_list = []

    for row in rows:
        # مرجوعی‌ها یا ردیف‌هایی که قیمت خرید ندارند → سود صفر
        if row.is_return or row.purchase_price <= 0:
            row.profit = 0
            row.tax_amount = 0
            update_list.append(row)
            continue

        tax = (row.commission_amount + row.processing_fee) // 10

        if row.sale_type == InvoiceRow.SALE_TYPE_CASH:
            total_cost = (
                row.purchase_price
                + row.commission_amount
                + row.shipping_fee
                + row.processing_fee
                + tax
            )
        else:
            total_cost = (
                row.purchase_price
                + row.platform_dev_revenue
                + row.commission_amount
                + row.shipping_fee
                + row.processing_fee
                + tax
            )

        row.tax_amount = tax
        row.profit = row.sale_amount - total_cost
        update_list.append(row)

    if update_list:
        InvoiceRow.objects.bulk_update(update_list, ["profit", "tax_amount"])


# ----------------------------------------------------------------------
#  لندینگ / صفحه معرفی
# ----------------------------------------------------------------------


def landing(request):
    """
    صفحه معرفی DigiHesabYar
    templates/digihesabyar/landing.html
    """
    context = {}
    
    # اگر کاربر لاگین کرده، آمار را اضافه می‌کنیم
    if request.user.is_authenticated:
        wallet = _get_or_create_wallet(request.user)
        invoice_count = InvoiceFile.objects.filter(user=request.user).count()
        paid_invoices = InvoiceFile.objects.filter(user=request.user, is_paid=True).count()
        pending_invoices = InvoiceFile.objects.filter(user=request.user, status=InvoiceFile.STATUS_PENDING).count()
        
        context.update({
            "wallet": wallet,
            "invoice_count": invoice_count,
            "paid_invoices": paid_invoices,
            "pending_invoices": pending_invoices,
        })
    
    return render(request, "digihesabyar/landing.html", context)


# ----------------------------------------------------------------------
#  داشبورد: آپلود صورتحساب و لیست فایل‌ها
# ----------------------------------------------------------------------


@login_required
def dashboard(request):
    """
    داشبورد اصلی کاربر:
      - فرم آپلود فایل اکسل صورتحساب
      - لیست آخرین صورتحساب‌های کاربر
    """
    if request.method == "POST":
        form = InvoiceUploadForm(request.POST, request.FILES)
        if form.is_valid():
            title = request.POST.get("title") or "صورتحساب دیجی‌کالا"
            f = form.cleaned_data["original_file"]

            invoice = InvoiceFile.objects.create(
                user=request.user,
                title=title,
                original_file=f,
                status=InvoiceFile.STATUS_PENDING,
            )

            # پردازش فایل
            row_count, log_text = process_invoice_file(invoice)

            if invoice.status == InvoiceFile.STATUS_ERROR:
                messages.error(
                    request,
                    f"خطا در پردازش فایل: {invoice.error_message}",
                )
            else:
                messages.success(
                    request,
                    f"فایل با موفقیت پردازش شد. تعداد ردیف‌ها: {row_count}",
                )

            # بعد از پردازش موفق، کاربر را به صفحه ثبت قیمت خرید می‌بریم
            return redirect("digihesabyar:invoice_prices", invoice_id=invoice.id)
        else:
            messages.error(
                request,
                "فایل ارسال‌شده معتبر نیست، لطفاً خطاهای فرم را بررسی کنید.",
            )
    else:
        form = InvoiceUploadForm()

    invoices = (
        InvoiceFile.objects.filter(user=request.user)
        .select_related("user")
        .order_by("-uploaded_at")
    )

    return render(
        request,
        "digihesabyar/dashboard.html",
        {
            "invoices": invoices,
            "form": form,
        },
    )
# ----------------------------------------------------------------------
#  جزئیات یک صورتحساب
# ----------------------------------------------------------------------


@login_required
def invoice_detail(request, invoice_id: int):
    """
    نمایش جزئیات یک صورتحساب:
      - ردیف‌ها
      - وضعیت پرداخت
      - خلاصه‌ای از مقادیر (فقط ردیف‌های غیرمرجوعی برای جمع‌ها)
    """
    invoice = get_object_or_404(InvoiceFile, id=invoice_id, user=request.user)

    rows = InvoiceRow.objects.filter(invoice=invoice).order_by("sale_type", "order_id")

    rows_for_summary = rows.filter(is_return=False)

    agg = rows_for_summary.aggregate(
        total_sale=models.Sum("sale_amount"),
        total_profit=models.Sum("profit"),
        total_commission=models.Sum("commission_amount"),
        total_shipping=models.Sum("shipping_fee"),
        total_processing=models.Sum("processing_fee"),
        total_platform_dev=models.Sum("platform_dev_revenue"),
    )

    totals = {k: v or 0 for k, v in agg.items()}

    wallet = _get_or_create_wallet(request.user)

    return render(
        request,
        "digihesabyar/invoice_detail.html",
        {
            "invoice": invoice,
            "rows": rows,
            "totals": totals,
            "wallet": wallet,
        },
    )


# ----------------------------------------------------------------------
#  ثبت / ویرایش قیمت خرید DKPCها برای یک صورتحساب
# ----------------------------------------------------------------------


@login_required
def invoice_prices(request, invoice_id: int):
    """
    صفحه‌ای برای نمایش لیست DKPCهای این صورتحساب و ثبت/ویرایش قیمت خرید هرکدام.
    دو روش:
      ۱) فرم وب (فیلدهای price_...)
      ۲) آپلود فایل اکسل قیمت خرید (price_excel)
    """
    invoice = get_object_or_404(InvoiceFile, id=invoice_id, user=request.user)

    # فقط ردیف‌های غیرمرجوعی برای تعیین DKPCها
    rows = InvoiceRow.objects.filter(invoice=invoice, is_return=False)

    summary = (
        rows.values("dkpc", "title")
        .annotate(
            count=models.Count("id"),
            total_sale=models.Sum("sale_amount"),
        )
        .order_by("dkpc")
    )

    dkpc_list = [item["dkpc"] for item in summary]

    existing_prices = {
        p.dkpc: p.purchase_price
        for p in ProductPrice.objects.filter(user=request.user, dkpc__in=dkpc_list)
    }

    upload_error = None
    min_purchase_price = 1000

    def parse_price_value(raw):
        """
        تبدیل مقدار خام به int. اگر نامعتبر بود → None
        """
        if raw in ("", None):
            return None
        try:
            value = normalize_number(raw)
        except Exception:
            return None
        return value

    # ----------------------- آپلود اکسل -----------------------
    if request.method == "POST" and "price_excel" in request.FILES:
        try:
            df = pd.read_excel(request.FILES["price_excel"])
        except Exception:
            messages.error(request, "خواندن فایل اکسل قیمت‌ها با مشکل مواجه شد.")
            return redirect("digihesabyar:invoice_prices", invoice_id=invoice.id)

        cols = [str(c).strip() for c in df.columns]

        dkpc_col = next((c for c in cols if "dkpc" in c.lower()), None)
        price_col = next((c for c in cols if "price" in c.lower()), None)

        if not dkpc_col or not price_col:
            messages.error(
                request, "ستون‌های DKPC و price در فایل اکسل پیدا نشد."
            )
            return redirect("digihesabyar:invoice_prices", invoice_id=invoice.id)

        for _, row_df in df.iterrows():
            dkpc_val = str(row_df.get(dkpc_col, "")).strip()
            if dkpc_val == "":
                continue

            raw_price = row_df.get(price_col)
            price_val = parse_price_value(raw_price)

            if price_val is None:
                continue

            if price_val < 0:
                upload_error = f"قیمت {dkpc_val} نمی‌تواند منفی باشد."
                break

            if price_val < min_purchase_price:
                upload_error = f"قیمت {dkpc_val} خیلی کوچک است."
                break

            ProductPrice.objects.update_or_create(
                user=request.user,
                dkpc=dkpc_val,
                defaults={"purchase_price": price_val},
            )

            InvoiceRow.objects.filter(invoice=invoice, dkpc=dkpc_val).update(
                purchase_price=price_val
            )

        if not upload_error:
            recalc_profit(invoice)
            messages.success(request, "قیمت‌ها ثبت و سود/زیان محاسبه شد.")
            return redirect("digihesabyar:invoice_detail", invoice_id=invoice.id)

        messages.error(request, upload_error)
        return redirect("digihesabyar:invoice_prices", invoice_id=invoice.id)

    # ----------------------- فرم وب -----------------------
    if request.method == "POST" and "price_excel" not in request.FILES:
        has_error = False

        for item in summary:
            dkpc = item["dkpc"]
            raw_val = request.POST.get(f"price_{dkpc}", "")
            price_val = parse_price_value(raw_val)

            if price_val is None:
                messages.error(
                    request,
                    f"قیمت وارد شده برای {dkpc} نامعتبر است.",
                )
                has_error = True
                continue

            if price_val < 0:
                messages.error(
                    request,
                    f"قیمت وارد شده برای {dkpc} نمی‌تواند منفی باشد.",
                )
                has_error = True
                continue

            if price_val < min_purchase_price:
                messages.error(
                    request,
                    f"قیمت وارد شده برای {dkpc} خیلی کوچک است.",
                )
                has_error = True
                continue

            ProductPrice.objects.update_or_create(
                user=request.user,
                dkpc=dkpc,
                defaults={
                    "purchase_price": price_val,
                    "title": item.get("title") or "",
                },
            )

            InvoiceRow.objects.filter(invoice=invoice, dkpc=dkpc).update(
                purchase_price=price_val
            )

        if not has_error:
            recalc_profit(invoice)
            messages.success(request, "قیمت‌ها ثبت و سود/زیان محاسبه شد.")
            return redirect("digihesabyar:invoice_detail", invoice_id=invoice.id)

    return render(
        request,
        "digihesabyar/invoice_prices.html",
        {
            "invoice": invoice,
            "summary": summary,
            "existing_prices": existing_prices,
            "upload_error": upload_error,
            "min_purchase_price": min_purchase_price,
        },
    )


# ----------------------------------------------------------------------
#  پرداخت هزینه صورتحساب از کیف پول
# ----------------------------------------------------------------------


@login_required
def invoice_pay(request, invoice_id: int):
    """
    صفحه پرداخت هزینه پردازش این صورتحساب از کیف پول.
    - اگر invoice.is_paid == True → ریدایرکت به invoice_detail
    - اگر موجودی کم باشد → نمایش کمبود و لینک رفتن به wallet_topup
    - روی POST و کافی بودن موجودی → برداشت از کیف پول + ثبت تراکنش + is_paid=True
    """
    invoice = get_object_or_404(InvoiceFile, id=invoice_id, user=request.user)

    if invoice.is_paid:
        messages.info(request, "این صورتحساب قبلاً پرداخت شده است.")
        return redirect("digihesabyar:invoice_detail", invoice_id=invoice.id)

    wallet = _get_or_create_wallet(request.user)
    price = invoice.processing_price or 0
    balance = wallet.balance
    needed = max(price - balance, 0)

    if request.method == "POST":
        if price <= 0:
            messages.error(request, "هزینه پردازش برای این صورتحساب تنظیم نشده است.")
            return redirect("digihesabyar:invoice_detail", invoice_id=invoice.id)

        if wallet.balance < price:
            messages.error(request, "موجودی کیف پول کافی نیست.")
            return redirect("digihesabyar:invoice_pay", invoice_id=invoice.id)

        with transaction.atomic():
            wallet = _get_or_create_wallet(request.user)
            if wallet.balance < price:
                messages.error(request, "موجودی کیف پول کافی نیست.")
                return redirect("digihesabyar:invoice_pay", invoice_id=invoice.id)

            wallet.balance -= price
            wallet.save(update_fields=["balance"])

            WalletTransaction.objects.create(
                wallet=wallet,
                invoice=invoice,
                type=WalletTransaction.TYPE_DEBIT,
                amount=price,
                description=f"پرداخت هزینه پردازش صورتحساب #{invoice.id}",
            )

            invoice.is_paid = True
            invoice.save(update_fields=["is_paid"])

        messages.success(request, "پرداخت با موفقیت انجام شد.")
        return redirect("digihesabyar:invoice_detail", invoice_id=invoice.id)

    return render(
        request,
        "digihesabyar/invoice_pay.html",
        {
            "invoice": invoice,
            "wallet": wallet,
            "price": price,
            "needed": needed,
        },
    )


# ----------------------------------------------------------------------
#  کیف پول و شارژ دستی (ماک برای تست)
# ----------------------------------------------------------------------


@login_required
def wallet_view(request):
    """
    صفحه نمایش کیف پول کاربر:
      - موجودی
      - لیست تراکنش‌ها
      - لینک به شارژ کیف پول
    """
    wallet = _get_or_create_wallet(request.user)
    transactions = wallet.transactions.all().order_by("-created_at")[:50]

    return render(
        request,
        "digihesabyar/wallet.html",
        {
            "wallet": wallet,
            "transactions": transactions,
        },
    )


@login_required
def wallet_topup_view(request):
    """
    شارژ کیف پول (نسخه ماک/آزمایشی، بدون درگاه).
    فرم ساده:
      - amount (ریال)
    """
    wallet = _get_or_create_wallet(request.user)

    if request.method == "POST":
        raw_amount = request.POST.get("amount", "")
        amount = normalize_number(raw_amount)

        if amount <= 0:
            messages.error(request, "مبلغ شارژ نامعتبر است.")
            return redirect("digihesabyar:wallet_topup")

        with transaction.atomic():
            wallet.balance += amount
            wallet.save(update_fields=["balance"])

            WalletTransaction.objects.create(
                wallet=wallet,
                invoice=None,
                type=WalletTransaction.TYPE_CREDIT,
                amount=amount,
                description="شارژ کیف پول (ماک / تست)",
            )

        messages.success(request, "کیف پول با موفقیت شارژ شد.")
        next_url = request.GET.get("next")
        if next_url:
            return redirect(next_url)

        return redirect("digihesabyar:wallet")

    return render(
        request,
        "digihesabyar/wallet_topup.html",
        {
            "wallet": wallet,
        },
    )


# ----------------------------------------------------------------------
#  ماشین‌حساب رایگان
# ----------------------------------------------------------------------


def calculator(request):
    """
    ماشین‌حساب ساده برای محاسبه سود/زیان یک آیتم تکی.
    template: digihesabyar/calculator.html
    
    این view فقط صفحه را نمایش می‌دهد و محاسبات در سمت کلاینت (JavaScript) انجام می‌شود.
    اگر در آینده نیاز به ذخیره نتایج یا API بود، می‌توان POST handling را اضافه کرد.
    """
    return render(
        request,
        "digihesabyar/calculator.html",
    )


# ----------------------------------------------------------------------
#  خروجی اکسل سود و زیان
# ----------------------------------------------------------------------


@login_required
def export_invoice_excel(request, invoice_id: int):
    """
    خروجی اکسل برای یک صورتحساب:
      - شیت "فروش نقدی"
      - شیت "فروش اعتباری"
      - شیت "خلاصه"
      - شیت "خلاصه DKPC"
    منطق:
      - برای مرجوعی‌ها، همه اعداد صفر و وضعیت "مرجوعی"
      - مرجوعی‌ها وارد جمع کل نمی‌شوند
      - دانلود اکسل فقط برای صورتحساب‌های پرداخت‌شده مجاز است.
    """
    invoice = get_object_or_404(InvoiceFile, id=invoice_id, user=request.user)

    # اگر هنوز هزینه پردازش پرداخت نشده، اجازه دانلود اکسل نداریم
    if not invoice.is_paid:
        messages.error(
            request,
            "برای دانلود خروجی اکسل، لطفاً ابتدا هزینه پردازش این صورتحساب را پرداخت کنید.",
        )
        return redirect("digihesabyar:invoice_pay", invoice_id=invoice.id)

    rows = InvoiceRow.objects.filter(invoice=invoice).order_by("sale_type", "order_id")

    cash_rows = []
    credit_rows = []

    dkpc_summary = {}

    total_sale = 0
    total_profit = 0
    total_commission = 0
    total_shipping = 0
    total_processing = 0
    total_platform_dev = 0

    for r in rows:
        base = r.get_export_row()

        if r.is_return:
            # فقط برای نمایش در شیت‌ها؛ در جمع‌ها حساب نمی‌کنیم
            if r.sale_type == InvoiceRow.SALE_TYPE_CASH:
                cash_rows.append(base)
            else:
                credit_rows.append(base)
            continue

        total_sale += r.sale_amount
        total_profit += r.profit
        total_commission += r.commission_amount
        total_shipping += r.shipping_fee
        total_processing += r.processing_fee
        total_platform_dev += r.platform_dev_revenue

        if r.dkpc not in dkpc_summary:
            dkpc_summary[r.dkpc] = {
                "title": r.title,
                "count": 0,
                "sale": 0,
                "profit": 0,
            }

        dkpc_summary[r.dkpc]["count"] += 1
        dkpc_summary[r.dkpc]["sale"] += r.sale_amount
        dkpc_summary[r.dkpc]["profit"] += r.profit

        if r.sale_type == InvoiceRow.SALE_TYPE_CASH:
            cash_rows.append(base)
        else:
            credit_rows.append(base)

    df_cash = pd.DataFrame(cash_rows)
    df_credit = pd.DataFrame(credit_rows)

    df_summary = pd.DataFrame(
        [
            {
                "total_sale": total_sale,
                "total_profit": total_profit,
                "total_commission": total_commission,
                "total_shipping": total_shipping,
                "total_processing": total_processing,
                "total_platform_dev": total_platform_dev,
            }
        ]
    )

    dkpc_rows = [
        {
            "dkpc": dk,
            "title": info["title"],
            "count": info["count"],
            "sale": info["sale"],
            "profit": info["profit"],
        }
        for dk, info in dkpc_summary.items()
    ]
    df_dkpc = pd.DataFrame(dkpc_rows)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_cash.to_excel(writer, sheet_name="فروش نقدی", index=False)
        df_credit.to_excel(writer, sheet_name="فروش اعتباری", index=False)
        df_summary.to_excel(writer, sheet_name="خلاصه", index=False)
        df_dkpc.to_excel(writer, sheet_name="خلاصه DKPC", index=False)

    buffer.seek(0)

    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="invoice_{invoice.id}.xlsx"'
    )
    return response
