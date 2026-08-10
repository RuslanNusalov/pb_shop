from django import forms
from django.utils.html import strip_tags

INPUT_CLASS = 'w-full px-4 py-3 border border-black rounded-none text-black placeholder-gray-500 focus:outline-none focus:border-black'

class OrderForm(forms.Form):
    first_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Имя *'
        })
    )
    last_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Фамилия *'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Эл. почта *',
            'readonly': 'readonly'
        })
    )
    address = forms.CharField(
        max_length=255,
        # ✅ required=False удалён → поле стало обязательным
        widget=forms.TextInput(attrs={
            'class': f'{INPUT_CLASS} pr-10',
            'placeholder': 'Адрес *'
        })
    )
    city = forms.CharField(
        max_length=100,
        # ✅ required=False удалён
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Город *'
        })
    )
    region = forms.CharField(
        max_length=100,
        # ✅ required=False удалён
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Регион *'
        })
    )
    postal_code = forms.CharField(
        max_length=20,
        # ✅ required=False удалён
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Индекс *'
        })
    )
    phone = forms.CharField(
        max_length=15,
        # ✅ required=False удалён
        widget=forms.TextInput(attrs={
            'class': f'{INPUT_CLASS} pr-10',
            'placeholder': 'Телефон *'
        })
    )
    special_instructions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Комментарий к заказу',
            'rows': 3,
        })
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email
            self.fields['address'].initial = user.address
            self.fields['city'].initial = user.city
            self.fields['region'].initial = user.region
            self.fields['postal_code'].initial = user.postal_code
            self.fields['phone'].initial = user.phone

    def clean(self):
        cleaned_data = super().clean()
        for field in ['address', 'city', 'region', 'postal_code', 'phone', 'special_instructions']:
            if cleaned_data.get(field):
                cleaned_data[field] = strip_tags(cleaned_data[field])
        return cleaned_data