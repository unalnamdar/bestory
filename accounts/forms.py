from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class StyledFormMixin:
    """Design-system classes, accessibility hooks and a helper to flag invalid fields."""

    def style_fields(self):
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "input"
            field.widget.attrs["aria-describedby"] = f"id_{name}_hint id_{name}_error"

    def mark_invalid(self):
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"


class RegisterForm(StyledFormMixin, UserCreationForm):
    error_messages = {"password_mismatch": "Parolalar eşleşmiyor."}

    class Meta:
        model = User
        fields = ("username", "email")
        labels = {"username": "Kullanıcı adı", "email": "E-posta"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = (
            "3-20 karakter; harf, rakam, alt çizgi (_) ve nokta (.) kullanabilirsin. "
            "Başkaları yalnızca bunu görür."
        )
        self.fields["email"].help_text = "Herkese açık gösterilmez, yalnızca sen görürsün."
        self.fields["email"].required = True
        self.fields["password1"].label = "Parola"
        self.fields["password2"].label = "Parola (tekrar)"
        self.fields["password2"].help_text = ""
        self.fields["username"].widget.attrs.update(autocomplete="username", autocapitalize="none", spellcheck="false")
        self.fields["email"].widget.attrs.update(autocomplete="email")
        self.fields["password1"].widget.attrs.update(autocomplete="new-password")
        self.fields["password2"].widget.attrs.update(autocomplete="new-password")
        self.style_fields()

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Bu kullanıcı adı zaten alınmış.", code="unique")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Bu e-posta adresi zaten kayıtlı.", code="unique")
        return email


class LoginForm(StyledFormMixin, forms.Form):
    identifier = forms.CharField(label="E-posta veya kullanıcı adı", max_length=254, strip=True)
    password = forms.CharField(label="Parola", strip=False, widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["identifier"].widget.attrs.update(autocomplete="username", autocapitalize="none", spellcheck="false")
        self.fields["password"].widget.attrs.update(autocomplete="current-password")
        self.style_fields()
