from django.contrib import admin

from .models import (
    InvoiceFile,
    InvoiceRow,
    ProductPrice,
    PricingTier,
    Wallet,
    WalletTransaction,
    Coupon,
)


@admin.register(InvoiceFile)
class InvoiceFileAdmin(admin.ModelAdmin):
    # فقط فیلدهای مطمئن و ساده
    list_display = ("id", "user", "title", "status", "is_paid", "row_count", "processing_price", "paid_amount", "coupon_code")
    list_filter = ("status", "is_paid", "uploaded_at")
    search_fields = ("title", "user__username", "user__email", "coupon_code")
    readonly_fields = ("uploaded_at", "created_at", "row_count")
    date_hierarchy = "uploaded_at"
    
    actions = ["mark_as_paid", "mark_as_unpaid", "recalculate_prices"]
    
    def mark_as_paid(self, request, queryset):
        """علامت‌گذاری صورتحساب‌های انتخاب شده به عنوان پرداخت شده"""
        count = queryset.update(is_paid=True)
        self.message_user(request, f"{count} صورتحساب به عنوان پرداخت شده علامت‌گذاری شد.")
    mark_as_paid.short_description = "علامت‌گذاری به عنوان پرداخت شده"
    
    def mark_as_unpaid(self, request, queryset):
        """علامت‌گذاری صورتحساب‌های انتخاب شده به عنوان پرداخت نشده"""
        count = queryset.update(is_paid=False)
        self.message_user(request, f"{count} صورتحساب به عنوان پرداخت نشده علامت‌گذاری شد.")
    mark_as_unpaid.short_description = "علامت‌گذاری به عنوان پرداخت نشده"
    
    def recalculate_prices(self, request, queryset):
        """محاسبه مجدد قیمت پردازش بر اساس تعرفه‌ها"""
        from .models import PricingTier
        from django.db.models import Q
        
        updated = 0
        for invoice in queryset:
            if invoice.row_count > 0:
                tier = PricingTier.objects.filter(
                    Q(min_rows__lte=invoice.row_count) &
                    (Q(max_rows__gte=invoice.row_count) | Q(max_rows__isnull=True))
                ).order_by("min_rows").first()
                if tier:
                    invoice.processing_price = tier.price_per_invoice
                    invoice.save(update_fields=["processing_price"])
                    updated += 1
        self.message_user(request, f"قیمت {updated} صورتحساب به‌روزرسانی شد.")
    recalculate_prices.short_description = "محاسبه مجدد قیمت پردازش"


@admin.register(InvoiceRow)
class InvoiceRowAdmin(admin.ModelAdmin):
    list_display = ("id", "invoice", "sale_type", "order_id", "dkpc", "title", "is_return")
    list_filter = ("sale_type", "is_return")
    search_fields = ("order_id", "dkpc", "title")


@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "dkpc", "purchase_price")
    search_fields = ("dkpc", "title", "user__username", "user__email")


@admin.register(PricingTier)
class PricingTierAdmin(admin.ModelAdmin):
    list_display = ("name", "min_rows", "max_rows", "price_per_invoice")
    ordering = ("min_rows",)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "balance")
    search_fields = ("user__username", "user__email")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "wallet", "invoice", "type", "amount", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("wallet__user__username", "wallet__user__email", "description")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    # اینجا عمداً 'percent' گذاشتم، نه 'percentage'
    list_display = ("code", "percent", "is_active", "used_count", "max_uses", "valid_from", "valid_to")
    search_fields = ("code", "description")
    list_filter = ("is_active", "valid_from", "valid_to")
    readonly_fields = ("used_count",)
    date_hierarchy = "valid_from"
    
    actions = ["activate_coupons", "deactivate_coupons", "reset_usage_count"]
    
    def activate_coupons(self, request, queryset):
        """فعال کردن کوپن‌های انتخاب شده"""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} کوپن فعال شد.")
    activate_coupons.short_description = "فعال کردن کوپن‌ها"
    
    def deactivate_coupons(self, request, queryset):
        """غیرفعال کردن کوپن‌های انتخاب شده"""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} کوپن غیرفعال شد.")
    deactivate_coupons.short_description = "غیرفعال کردن کوپن‌ها"
    
    def reset_usage_count(self, request, queryset):
        """بازنشانی تعداد استفاده کوپن‌ها"""
        count = queryset.update(used_count=0)
        self.message_user(request, f"تعداد استفاده {count} کوپن بازنشانی شد.")
    reset_usage_count.short_description = "بازنشانی تعداد استفاده"
