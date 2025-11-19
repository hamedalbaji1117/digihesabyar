from django.db import models
from django.conf import settings
from django.db.models import Q
from django.utils import timezone


class PricingTier(models.Model):
    """
    تعرفه پردازش صورتحساب بر اساس تعداد ردیف‌های فروش (row_count).
    مثال:
      - تا 500 ردیف = 490000
      - 500 تا 1000 ردیف = 890000
      - بیشتر از 1000 ردیف = 1290000
    """

    name = models.CharField(max_length=100, verbose_name="نام تعرفه")
    min_rows = models.PositiveIntegerField(verbose_name="حداقل تعداد ردیف")
    max_rows = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="حداکثر تعداد ردیف (خالی = بدون سقف)",
    )
    price_per_invoice = models.PositiveBigIntegerField(
        verbose_name="هزینه این صورتحساب (ریال)"
    )

    class Meta:
        verbose_name = "تعرفه صورتحساب"
        verbose_name_plural = "تعرفه‌های صورتحساب"
        ordering = ["min_rows"]

    def __str__(self) -> str:
        if self.max_rows:
            return f"{self.name} ({self.min_rows} تا {self.max_rows} ردیف)"
        return f"{self.name} (از {self.min_rows} ردیف به بالا)"


class InvoiceFile(models.Model):
    """
    فایل اکسل صورتحساب دیجی‌کالا که توسط کاربر آپلود می‌شود.
    """

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"

    STATUS_CHOICES = [
        (STATUS_PENDING, "در صف پردازش"),
        (STATUS_PROCESSING, "در حال پردازش"),
        (STATUS_DONE, "پردازش‌شده"),
        (STATUS_ERROR, "خطا در پردازش"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="invoice_files",
        verbose_name="کاربر",
    )

    title = models.CharField(max_length=255, verbose_name="عنوان")
    original_file = models.FileField(
        upload_to="invoices/",
        verbose_name="فایل اکسل صورتحساب",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ آپلود")

    row_count = models.PositiveIntegerField(default=0, verbose_name="تعداد ردیف‌ها")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="وضعیت پردازش",
    )
    error_message = models.TextField(blank=True, verbose_name="متن خطا (در صورت وجود)")

    processing_price = models.PositiveBigIntegerField(
        default=0,
        verbose_name="هزینه پردازش این صورتحساب (ریال)",
    )
    is_paid = models.BooleanField(default=False, verbose_name="پرداخت شده است؟")
    
    coupon_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="کد تخفیف استفاده‌شده",
    )
    paid_amount = models.PositiveBigIntegerField(
        default=0,
        verbose_name="مبلغ پرداخت‌شده (ریال)",
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="تاریخ ایجاد رکورد"
    )

    class Meta:
        verbose_name = "فایل صورتحساب"
        verbose_name_plural = "فایل‌های صورتحساب"
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.user})"

    def calculate_price_from_tiers(self) -> int:
        """
        با توجه به تعداد ردیف‌ها (row_count) و جدول PricingTier،
        قیمت پردازش این صورتحساب را برمی‌گرداند.
        """
        if self.row_count <= 0:
            return 0

        qs = PricingTier.objects.order_by("min_rows")
        tier = qs.filter(
            Q(min_rows__lte=self.row_count)
            & (Q(max_rows__gte=self.row_count) | Q(max_rows__isnull=True))
        ).first()
        if tier:
            return tier.price_per_invoice
        return 0


class InvoiceRow(models.Model):
    """
    هر ردیف فروش / برگشت از فروش مربوط به یک صورتحساب.
    """

    SALE_TYPE_CASH = "cash"
    SALE_TYPE_CREDIT = "credit"

    SALE_TYPE_CHOICES = [
        (SALE_TYPE_CASH, "نقدی"),
        (SALE_TYPE_CREDIT, "اعتباری"),
    ]

    invoice = models.ForeignKey(
        InvoiceFile,
        on_delete=models.CASCADE,
        related_name="rows",
        verbose_name="صورتحساب",
    )

    sale_type = models.CharField(
        max_length=10,
        choices=SALE_TYPE_CHOICES,
        verbose_name="نوع فروش",
    )

    order_id = models.CharField(
        max_length=100,
        verbose_name="شماره سفارش",
    )
    dkpc = models.CharField(
        max_length=100,
        verbose_name="کد تنوع (DKPC)",
    )
    title = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="عنوان تنوع",
    )

    sale_amount = models.BigIntegerField(
        default=0,
        verbose_name="قیمت فروش (ریال)",
    )
    purchase_price = models.BigIntegerField(
        default=0,
        verbose_name="قیمت خرید (ریال)",
    )

    commission_amount = models.BigIntegerField(
        default=0,
        verbose_name="کمیسیون (ریال)",
    )
    shipping_fee = models.BigIntegerField(
        default=0,
        verbose_name="هزینه ارسال (ریال)",
    )
    processing_fee = models.BigIntegerField(
        default=0,
        verbose_name="هزینه پردازش (ریال)",
    )
    platform_dev_revenue = models.BigIntegerField(
        default=0,
        verbose_name="درآمد توسعه پلتفرم (ریال)",
    )
    tax_amount = models.BigIntegerField(
        default=0,
        verbose_name="مالیات خدمات (ریال)",
    )

    profit = models.BigIntegerField(
        default=0,
        verbose_name="سود / زیان (ریال)",
    )

    is_return = models.BooleanField(
        default=False,
        verbose_name="مرجوعی است؟",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    # -------------------------------
    # پراپرتی‌های کمکی برای نمایش
    # -------------------------------
    @property
    def sale_type_label(self):
        """برچسب نوع فروش (نقدی / اعتباری)."""
        return "نقدی" if self.sale_type == self.SALE_TYPE_CASH else "اعتباری"

    @property
    def status_text(self):
        """اگر مرجوعی باشد، 'مرجوعی' وگرنه 'فروش رفته'."""
        return "مرجوعی" if self.is_return else "فروش رفته"

    @property
    def profit_display(self):
        """برای مرجوعی‌ها همیشه ۰؛ برای بقیه مقدار سود."""
        return 0 if self.is_return else self.profit

    @property
    def profit_percent_str(self):
        """برای مرجوعی‌ها یا وقتی خرید صفر است، رشتهٔ خالی."""
        if self.is_return or self.purchase_price <= 0:
            return ""
        try:
            p = (self.profit / self.purchase_price) * 100
            return f"{p:.1f}"
        except Exception:
            return ""

    def get_export_row(self):
        """خروجی آماده برای اکسل (بسته به مرجوعی بودن)."""
        if self.is_return:
            return {
                "order_id": self.order_id,
                "dkpc": self.dkpc,
                "title": self.title,
                "status": "مرجوعی",
                "sale": 0,
                "purchase": 0,
                "commission": 0,
                "shipping": 0,
                "processing": 0,
                "platform_dev": 0,
                "tax": 0,
                "profit": 0,
                "profit_percent": "",
            }

        return {
            "order_id": self.order_id,
            "dkpc": self.dkpc,
            "title": self.title,
            "status": "فروش رفته",
            "sale": self.sale_amount,
            "purchase": self.purchase_price,
            "commission": self.commission_amount,
            "shipping": self.shipping_fee,
            "processing": self.processing_fee,
            "platform_dev": self.platform_dev_revenue,
            "tax": self.tax_amount,
            "profit": self.profit,
            "profit_percent": self.profit_percent_str,
        }

    class Meta:
        verbose_name = "ردیف صورتحساب"
        verbose_name_plural = "ردیف‌های صورتحساب"
        ordering = ["invoice", "sale_type", "order_id", "dkpc"]

    def __str__(self) -> str:
        return f"{self.invoice_id} - {self.order_id} - {self.dkpc}"


class ProductPrice(models.Model):
    """
    قیمت خرید ثبت‌شده برای هر DKPC به تفکیک کاربر.
    برای هر (کاربر + DKPC) فقط یک رکورد نگه می‌داریم.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_prices",
        verbose_name="کاربر",
    )
    dkpc = models.CharField(
        max_length=100,
        verbose_name="کد تنوع (DKPC)",
    )
    title = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="عنوان تنوع",
    )
    purchase_price = models.BigIntegerField(
        default=0,
        verbose_name="قیمت خرید (ریال)",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین بروزرسانی",
    )

    class Meta:
        unique_together = ("user", "dkpc")
        verbose_name = "قیمت خرید کالا"
        verbose_name_plural = "قیمت‌های خرید کالاها"

    def __str__(self) -> str:
        return f"{self.user} - {self.dkpc} - {self.purchase_price}"


class Wallet(models.Model):
    """
    کیف پول هر کاربر برای پرداخت هزینه پردازش صورتحساب‌ها.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
        verbose_name="کاربر",
    )
    balance = models.BigIntegerField(default=0, verbose_name="موجودی (ریال)")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        verbose_name = "کیف پول"
        verbose_name_plural = "کیف پول‌ها"

    def __str__(self) -> str:
        return f"{self.user} - {self.balance} ریال"


class WalletTransaction(models.Model):
    """
    لاگ تراکنش‌های کیف پول (واریز/برداشت).
    """

    TYPE_CREDIT = "credit"
    TYPE_DEBIT = "debit"

    TYPE_CHOICES = [
        (TYPE_CREDIT, "واریز"),
        (TYPE_DEBIT, "برداشت"),
    ]

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="کیف پول",
    )
    invoice = models.ForeignKey(
        InvoiceFile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_transactions",
        verbose_name="صورتحساب مربوطه (در صورت وجود)",
    )
    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        verbose_name="نوع تراکنش",
    )
    amount = models.BigIntegerField(verbose_name="مبلغ (ریال)")
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="توضیحات",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    class Meta:
        verbose_name = "تراکنش کیف پول"
        verbose_name_plural = "تراکنش‌های کیف پول"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        sign = "+" if self.type == self.TYPE_CREDIT else "-"
        return f"{self.wallet.user} | {sign}{abs(self.amount)} ({self.get_type_display()})"


class Coupon(models.Model):
    """
    کوپن تخفیف برای هزینه پردازش صورتحساب‌ها.
    مثال: 10٪، 20٪، ...
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="کد کوپن",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="توضیحات",
    )

    percent = models.PositiveIntegerField(
        default=0,
        verbose_name="درصد تخفیف (۰ تا ۱۰۰)",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال است؟",
    )

    valid_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="معتبر از تاریخ",
    )
    valid_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="معتبر تا تاریخ",
    )

    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="حداکثر دفعات استفاده (خالی = بدون محدودیت)",
    )
    used_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد استفاده شده",
    )

    class Meta:
        verbose_name = "کوپن تخفیف"
        verbose_name_plural = "کوپن‌ها"

    def __str__(self):
        return self.code

    def is_valid_now(self) -> bool:
        """
        بررسی می‌کند آیا این کوپن همین الان معتبر است یا نه.
        شرط‌ها:
          - is_active = True
          - اگر valid_from ست شده، باید now >= valid_from
          - اگر valid_to ست شده، باید now <= valid_to
          - اگر max_uses ست شده، used_count < max_uses
        """
        if not self.is_active:
            return False

        now = timezone.now()

        if self.valid_from and now < self.valid_from:
            return False

        if self.valid_to and now > self.valid_to:
            return False

        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False

        return True
