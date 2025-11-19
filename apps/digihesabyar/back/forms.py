from django import forms
from .models import InvoiceFile


class InvoiceUploadForm(forms.ModelForm):
    class Meta:
        model = InvoiceFile
        fields = ["original_file"]
        labels = {
            "original_file": "فایل اکسل صورتحساب دیجی‌کالا",
        }

    def clean_original_file(self):
        file = self.cleaned_data.get("original_file")
        if file:
            # ✅ چک کردن پسوند فایل
            name = file.name.lower()
            if not (name.endswith(".xlsx") or name.endswith(".xls")):
                raise forms.ValidationError("فقط فایل اکسل با پسوند xlsx یا xls قبول می‌شود.")

            # ✅ چک کردن حداکثر حجم (۱۰ مگابایت)
            max_size_mb = 10
            if file.size > max_size_mb * 1024 * 1024:
                raise forms.ValidationError(
                    f"حجم فایل نباید بیشتر از {max_size_mb} مگابایت باشد."
                )

        return file
