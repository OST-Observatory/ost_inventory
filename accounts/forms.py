from django import forms
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from inventory.validators import reject_newlines

from .models import is_protected_group


class GroupNameForm(forms.Form):
    name = forms.CharField(max_length=150, label="Group name")

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance:
            self.fields["name"].initial = instance.name

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        reject_newlines(name, "Group name")
        if not name:
            raise ValidationError("Group name is required.")
        qs = Group.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A group with this name already exists.")
        if self.instance and is_protected_group(self.instance) and name != self.instance.name:
            raise ValidationError("This group is tied to login roles and cannot be renamed.")
        return name


class AddMemberForm(forms.Form):
    username = forms.CharField(max_length=150, label="Username")

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        reject_newlines(username, "Username")
        if not username:
            raise ValidationError("Username is required.")
        return username
