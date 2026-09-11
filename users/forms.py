from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Profile

class LoginForm(forms.Form):
    username = forms.CharField(max_length='16',label='Username')
    password = forms.CharField(label='Password', max_length='20', widget=forms.PasswordInput())
class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(label='Email')
    
    class Meta:
        model=User
        fields=['username','email', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email

class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(label='Email')
    class Meta:
        model = User
        fields=['username','email']

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['picture', 'first_name', 'last_name', 'bio']
        widgets = {
            # Protected media deliberately has no public ``url``. A plain file
            # input avoids ClearableFileInput dereferencing the stored image.
            'picture': forms.FileInput(),
        }
