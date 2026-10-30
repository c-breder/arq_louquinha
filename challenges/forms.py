from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from works.sanitize import autoparagraph, clean_html

from .models import Collection, Prompt


class CollectionForm(forms.ModelForm):
    closes_at = forms.DateTimeField(
        label=_("Prazo (opcional)"),
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = Collection
        fields = ["title", "slug", "kind", "description", "is_open", "is_moderated", "closes_at"]
        help_texts = {"slug": _("Aparece no endereço: /colecoes/<este-nome>/. Letras, números e hífen.")}
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["slug"]  # o endereço não muda depois de criado

    def clean_slug(self):
        slug = self.cleaned_data["slug"].lower()
        if slug in {"nova"}:
            raise ValidationError(_("Esse endereço é reservado."))
        return slug

    def clean_description(self):
        return clean_html(autoparagraph(self.cleaned_data["description"]))


class PromptForm(forms.ModelForm):
    class Meta:
        model = Prompt
        fields = ["text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if len(text) > 2000:
            raise ValidationError(_("Prompt longo demais."))
        return text


class AddWorkForm(forms.Form):
    collection = forms.SlugField(label=_("Endereço da coleção"))
    prompt = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def clean_collection(self):
        collection = Collection.objects.filter(slug=self.cleaned_data["collection"]).first()
        if collection is None:
            raise ValidationError(_("Coleção não encontrada."))
        if not collection.accepting:
            raise ValidationError(_("Esta coleção não está aceitando obras."))
        return collection
