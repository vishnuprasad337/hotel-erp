from django import forms
from django.forms import ModelForm
from django.core.exceptions import ValidationError
import re
from .models import Hotel



class HotelForm(ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter Password'}),
        required=True
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'}),
        required=True
    )

    class Meta:
        model = Hotel
        fields = [
            'hotel_name',
            'email',
            'owner_name',
            'address',
            'city',
            'property_type',
            'image',
            'description',
            'amenities'
        ]

        widgets = {
            'hotel_name': forms.TextInput(attrs={'placeholder': 'Enter Hotel Name...'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email Address...'}),
            'owner_name': forms.TextInput(attrs={'placeholder': 'Owner Full Name...'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'city': forms.TextInput(attrs={'placeholder': 'City...'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'amenities': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise ValidationError("Passwords do not match")

        return cleaned_data
        
        

        return cleaned_data
    def clean_schema_name(self):
        schema_name = self.cleaned_data.get('schema_name')

        if not schema_name:
            raise ValidationError("Subdomain is required.")

        schema_name = schema_name.lower()

        if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', schema_name):
            raise ValidationError(
            "Subdomains can only contain lowercase letters, numbers, and internal hyphens."
        )

        if Hotel.objects.filter(schema_name=schema_name).exists():
            raise ValidationError("This subdomain is already taken.")

        return schema_name