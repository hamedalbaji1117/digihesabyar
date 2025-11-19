# Generated manually to add coupon_code and paid_amount fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("digihesabyar", "0009_alter_wallet_options_alter_wallettransaction_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoicefile",
            name="coupon_code",
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name="کد تخفیف استفاده‌شده",
            ),
        ),
        migrations.AddField(
            model_name="invoicefile",
            name="paid_amount",
            field=models.PositiveBigIntegerField(
                default=0,
                verbose_name="مبلغ پرداخت‌شده (ریال)",
            ),
        ),
    ]

