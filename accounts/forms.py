from uuid import uuid4

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.images import process_image

from .models import Pseud, User


class SignupForm(forms.Form):
    # Campo extra no cadastro do allauth (e-mail e redes sociais)
    confirm_adult = forms.BooleanField(
        label=_("Confirmo que tenho 18 anos ou mais."),
        required=True,
    )

    def signup(self, request, user):
        user.adult_confirmed_at = timezone.now()
        user.save()


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["language", "hide_warnings", "hide_explicit", "allow_messages"]


class PseudForm(forms.ModelForm):
    avatar_upload = forms.FileField(
        label=_("Avatar"),
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )
    remove_avatar = forms.BooleanField(label=_("Remover avatar atual"), required=False)

    class Meta:
        model = Pseud
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.avatar_content = None
        self.fields["avatar_upload"].help_text = _(
            "JPG, PNG, GIF ou WebP, até %(max)d MB. Fica quadrado, em %(size)d×%(size)d."
        ) % {"max": settings.MAX_AVATAR_UPLOAD_MB, "size": settings.AVATAR_SIZE}
        if not self.instance.avatar:
            del self.fields["remove_avatar"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = self.user.pseuds.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError(_("Você já tem um pseudônimo com esse nome."))
        return name

    def clean_avatar_upload(self):
        upload = self.cleaned_data.get("avatar_upload")
        if upload:
            if upload.size > settings.MAX_AVATAR_UPLOAD_MB * 1024 * 1024:
                raise ValidationError(_("A imagem passa de %(max)d MB.") % {"max": settings.MAX_AVATAR_UPLOAD_MB})
            self.avatar_content, _width, _height = process_image(upload, square=settings.AVATAR_SIZE)
        return upload

    def save(self, commit=True):
        pseud = super().save(commit=False)
        pseud.user = self.user
        old_avatar = pseud.avatar.name if pseud.avatar else ""
        if self.cleaned_data.get("remove_avatar") or self.avatar_content:
            pseud.avatar = None
        if self.avatar_content:
            pseud.avatar.save(f"{uuid4().hex}.webp", self.avatar_content, save=False)
        pseud.save()
        if self.initial.get("name") and self.initial["name"] != pseud.name:
            from works.listing import queue_refresh

            # O nome aparece nos cards das listagens
            queue_refresh(pseud.authorships.values_list("work_id", flat=True))
        # Apaga o arquivo antigo quando o avatar mudou
        if old_avatar and old_avatar != (pseud.avatar.name if pseud.avatar else ""):
            pseud.avatar.storage.delete(old_avatar)
        return pseud


class DeleteAccountForm(forms.Form):
    WORKS_CHOICES = [
        ("orphan", _("Deixar minhas obras no arquivo, sem meu nome (conta órfã)")),
        ("delete", _("Apagar minhas obras junto com a conta")),
    ]

    works = forms.ChoiceField(label=_("O que fazer com suas obras?"), choices=WORKS_CHOICES, widget=forms.RadioSelect)
    confirm_username = forms.CharField(label=_("Digite seu nome de usuário para confirmar"))
    password = forms.CharField(label=_("Senha"), widget=forms.PasswordInput, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if not user.has_usable_password():
            del self.fields["password"]

    def clean_confirm_username(self):
        value = self.cleaned_data["confirm_username"].strip()
        if value != self.user.username:
            raise ValidationError(_("O nome não confere."))
        return value

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if not self.user.check_password(password):
            raise ValidationError(_("Senha incorreta."))
        return password
