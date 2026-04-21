from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('username', 'email', 'password1', 'password2'):
            self.fields[name].widget.attrs.setdefault('class', 'auth-input')
        self.fields['email'].required = False
        self.fields['username'].widget.attrs.setdefault('placeholder', '设置用户名')
        self.fields['email'].widget.attrs.setdefault('placeholder', '选填')
        self.fields['password1'].widget.attrs.setdefault('placeholder', '至少 8 位')
        self.fields['password2'].widget.attrs.setdefault('placeholder', '再次输入密码')
