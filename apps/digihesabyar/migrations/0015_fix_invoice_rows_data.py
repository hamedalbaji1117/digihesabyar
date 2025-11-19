from django.db import migrations


def normalize_invoice_rows(apps, schema_editor):
    InvoiceRow = apps.get_model("digihesabyar", "InvoiceRow")

    for row in InvoiceRow.objects.all().iterator():
        sale_amount = row.sale_amount or 0
        commission = row.commission_amount or 0
        shipping = row.shipping_fee or 0
        processing = row.processing_fee or 0
        platform_dev = row.platform_dev_revenue or 0
        purchase_price = row.purchase_price or 0

        # همه مقادیر را از نظر علامت مثبت می‌کنیم
        sale_amount = abs(sale_amount)
        commission = abs(commission)
        shipping = abs(shipping)
        processing = abs(processing)
        platform_dev = abs(platform_dev)

        # اگر ردیف مرجوعی است → همه مبالغ مالی صفر و سود صفر
        if row.is_return:
            row.sale_amount = 0
            row.commission_amount = 0
            row.shipping_fee = 0
            row.processing_fee = 0
            row.platform_dev_revenue = 0
            row.tax_amount = 0
            row.profit = 0
            row.save(
                update_fields=[
                    "sale_amount",
                    "commission_amount",
                    "shipping_fee",
                    "processing_fee",
                    "platform_dev_revenue",
                    "tax_amount",
                    "profit",
                ]
            )
            continue

        # برای ردیف‌های غیرمرجوعی:
        # مالیات = ۱۰٪ (کمیسیون + هزینه پردازش)
        tax = int((commission + processing) * 0.1)

        row.sale_amount = sale_amount
        row.commission_amount = commission
        row.shipping_fee = shipping
        row.processing_fee = processing
        row.platform_dev_revenue = platform_dev
        row.tax_amount = tax

        # محاسبه سود براساس نوع فروش
        total_cost = purchase_price + commission + shipping + processing + tax
        if row.sale_type == "credit":
            total_cost += platform_dev

        profit = sale_amount - total_cost
        row.profit = profit

        row.save(
            update_fields=[
                "sale_amount",
                "commission_amount",
                "shipping_fee",
                "processing_fee",
                "platform_dev_revenue",
                "tax_amount",
                "profit",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        # آخرین میگریشن اسکیما در پروژه‌ی تو
        ("digihesabyar", "0010_invoicefile_coupon_code_paid_amount"),
    ]

    operations = [
        migrations.RunPython(normalize_invoice_rows, migrations.RunPython.noop),
    ]
