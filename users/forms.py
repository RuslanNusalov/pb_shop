from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model, authenticate
from django.utils.html import strip_tags
from django.core.validators import RegexValidator


WIDGET_ATTRS = {'class': 'dotted-input w-full py-3 text-sm font-medium text-gray-900 placeholder-gray-500'}
User = get_user_model()
PHONE_VALIDATOR = RegexValidator(
    r'^(?:(?:\+7|8)[\s\-]*\(?\s*9\d{2}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2})?$',
    "Введите российский мобильный номер: +7 (9XX) XXX-XX-XX"
)


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, max_length=254, widget=forms.EmailInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ПОЧТА'}))
    first_name = forms.CharField(required=True, max_length=50, widget=forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ИМЯ'}))
    last_name = forms.CharField(required=True, max_length=50, widget=forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ФАМИЛИЯ'}))
    phone = forms.CharField(
        required=True,
        validators=[PHONE_VALIDATOR],
        widget=forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ТЕЛЕФОН'})
    )
    password1 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ПАРОЛЬ'})
    )
    password2 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ПОДТВЕРДИТЕ ПАРОЛЬ'})
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Эта почта уже используется.')
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            phone = ''.join(filter(str.isdigit, phone))
            if phone.startswith('8') and len(phone) == 11:
                phone = '+7' + phone[1:]
            elif phone.startswith('7') and len(phone) == 11:
                phone = '+' + phone
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError('Этот телефон уже используется.')
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user


class CustomUserLoginForm(AuthenticationForm):
    username = forms.CharField(label="Почта", widget=forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ПОЧТА'}))
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ПАРОЛЬ'})
    )

    def clean(self):
        email = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if email and password:
            self.user_cache = authenticate(self.request, username=email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError('Неверная почта или пароль.')
            elif not self.user_cache.is_active:
                raise forms.ValidationError('Этот аккаунт неактивен.')
        return self.cleaned_data


class CustomUserUpdateForm(forms.ModelForm):
    phone = forms.CharField(
    required=False,
    validators=[PHONE_VALIDATOR],
    widget=forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ТЕЛЕФОН'})
    )
    first_name = forms.CharField(
        required=True,
        max_length=50,
        widget=forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ИМЯ'})
    )
    last_name = forms.CharField(
        required=True,
        max_length=50,
        widget=forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ФАМИЛИЯ'})
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ПОЧТА'})
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email',
                  'address', 'city', 'region',
                  'postal_code', 'phone')
        widgets = {
            'address': forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'АДРЕС'}),
            'city': forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ГОРОД'}),
            'region': forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'РЕГИОН'}),
            'postal_code': forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'ИНДЕКС'}),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            phone = ''.join(filter(str.isdigit, phone))
            if phone.startswith('8') and len(phone) == 11:
                phone = '+7' + phone[1:]
            elif phone.startswith('7') and len(phone) == 11:
                phone = '+' + phone
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exclude(id=self.instance.id).exists():
            raise forms.ValidationError('Эта почта уже используется.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('email'):
            cleaned_data['email'] = self.instance.email
        for field in ['address', 'city', 'region',
                      'postal_code', 'phone']:
            if cleaned_data.get(field):
                cleaned_data[field] = strip_tags(cleaned_data[field])
        return cleaned_data
