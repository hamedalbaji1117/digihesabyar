from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import timedelta

from .models import (
    InvoiceFile,
    InvoiceRow,
    ProductPrice,
    PricingTier,
    Wallet,
    WalletTransaction,
    Coupon,
)
from .services import normalize_number, calculate_price_for_row_count

User = get_user_model()


class NormalizeNumberTests(TestCase):
    """تست‌های تابع normalize_number"""

    def test_normalize_persian_digits(self):
        """تبدیل ارقام فارسی به انگلیسی"""
        self.assertEqual(normalize_number("۱۲۳۴۵۶"), 123456)
        self.assertEqual(normalize_number("۹۸۷"), 987)

    def test_normalize_arabic_digits(self):
        """تبدیل ارقام عربی به انگلیسی"""
        self.assertEqual(normalize_number("١٢٣"), 123)

    def test_normalize_with_commas(self):
        """حذف کاما از اعداد"""
        self.assertEqual(normalize_number("1,234,567"), 1234567)
        self.assertEqual(normalize_number("۱۲۳٬۴۵۶"), 123456)

    def test_normalize_negative_numbers(self):
        """اعداد منفی"""
        self.assertEqual(normalize_number("-123"), -123)
        self.assertEqual(normalize_number("منفی 123"), -123)

    def test_normalize_invalid_input(self):
        """ورودی‌های نامعتبر"""
        self.assertEqual(normalize_number(""), 0)
        self.assertEqual(normalize_number("abc"), 0)
        self.assertEqual(normalize_number(None), 0)


class PricingTierTests(TestCase):
    """تست‌های مدل PricingTier"""

    def setUp(self):
        """ایجاد تعرفه‌های نمونه"""
        PricingTier.objects.create(
            name="تعرفه 1",
            min_rows=1,
            max_rows=500,
            price_per_invoice=490000,
        )
        PricingTier.objects.create(
            name="تعرفه 2",
            min_rows=501,
            max_rows=1000,
            price_per_invoice=890000,
        )
        PricingTier.objects.create(
            name="تعرفه 3",
            min_rows=1001,
            max_rows=None,
            price_per_invoice=1290000,
        )

    def test_calculate_price_for_small_invoice(self):
        """محاسبه قیمت برای صورتحساب کوچک"""
        price = calculate_price_for_row_count(100)
        self.assertEqual(price, 490000)

    def test_calculate_price_for_medium_invoice(self):
        """محاسبه قیمت برای صورتحساب متوسط"""
        price = calculate_price_for_row_count(750)
        self.assertEqual(price, 890000)

    def test_calculate_price_for_large_invoice(self):
        """محاسبه قیمت برای صورتحساب بزرگ"""
        price = calculate_price_for_row_count(2000)
        self.assertEqual(price, 1290000)

    def test_calculate_price_for_zero_rows(self):
        """محاسبه قیمت برای صفر ردیف"""
        price = calculate_price_for_row_count(0)
        self.assertEqual(price, 0)


class CouponTests(TestCase):
    """تست‌های مدل Coupon"""

    def setUp(self):
        """ایجاد کوپن نمونه"""
        self.coupon = Coupon.objects.create(
            code="TEST10",
            percent=10,
            is_active=True,
            max_uses=100,
        )

    def test_coupon_is_valid(self):
        """بررسی معتبر بودن کوپن"""
        self.assertTrue(self.coupon.is_valid_now())

    def test_coupon_expired(self):
        """بررسی منقضی شدن کوپن"""
        self.coupon.valid_to = timezone.now() - timedelta(days=1)
        self.coupon.save()
        self.assertFalse(self.coupon.is_valid_now())

    def test_coupon_not_started(self):
        """بررسی کوپنی که هنوز شروع نشده"""
        self.coupon.valid_from = timezone.now() + timedelta(days=1)
        self.coupon.save()
        self.assertFalse(self.coupon.is_valid_now())

    def test_coupon_max_uses_reached(self):
        """بررسی رسیدن به حداکثر استفاده"""
        self.coupon.used_count = 100
        self.coupon.save()
        self.assertFalse(self.coupon.is_valid_now())

    def test_coupon_inactive(self):
        """بررسی کوپن غیرفعال"""
        self.coupon.is_active = False
        self.coupon.save()
        self.assertFalse(self.coupon.is_valid_now())


class WalletTests(TestCase):
    """تست‌های مدل Wallet"""

    def setUp(self):
        """ایجاد کاربر و کیف پول"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.wallet = Wallet.objects.create(user=self.user, balance=1000000)

    def test_wallet_creation(self):
        """ایجاد کیف پول"""
        self.assertEqual(self.wallet.balance, 1000000)
        self.assertEqual(self.wallet.user, self.user)

    def test_wallet_transaction_credit(self):
        """تراکنش واریز"""
        transaction = WalletTransaction.objects.create(
            wallet=self.wallet,
            type=WalletTransaction.TYPE_CREDIT,
            amount=500000,
            description="شارژ تست",
        )
        self.assertEqual(transaction.type, WalletTransaction.TYPE_CREDIT)
        self.assertEqual(transaction.amount, 500000)

    def test_wallet_transaction_debit(self):
        """تراکنش برداشت"""
        invoice = InvoiceFile.objects.create(
            user=self.user,
            title="تست",
            original_file=SimpleUploadedFile("test.xlsx", b"test"),
            status=InvoiceFile.STATUS_DONE,
        )
        transaction = WalletTransaction.objects.create(
            wallet=self.wallet,
            invoice=invoice,
            type=WalletTransaction.TYPE_DEBIT,
            amount=200000,
            description="پرداخت تست",
        )
        self.assertEqual(transaction.type, WalletTransaction.TYPE_DEBIT)
        self.assertEqual(transaction.invoice, invoice)


class InvoiceFileTests(TestCase):
    """تست‌های مدل InvoiceFile"""

    def setUp(self):
        """ایجاد کاربر و صورتحساب"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.invoice = InvoiceFile.objects.create(
            user=self.user,
            title="صورتحساب تست",
            original_file=SimpleUploadedFile("test.xlsx", b"test"),
            status=InvoiceFile.STATUS_PENDING,
        )

    def test_invoice_creation(self):
        """ایجاد صورتحساب"""
        self.assertEqual(self.invoice.user, self.user)
        self.assertEqual(self.invoice.status, InvoiceFile.STATUS_PENDING)
        self.assertFalse(self.invoice.is_paid)

    def test_invoice_calculate_price(self):
        """محاسبه قیمت از تعرفه‌ها"""
        PricingTier.objects.create(
            name="تست",
            min_rows=1,
            max_rows=100,
            price_per_invoice=500000,
        )
        self.invoice.row_count = 50
        price = self.invoice.calculate_price_from_tiers()
        self.assertEqual(price, 500000)
