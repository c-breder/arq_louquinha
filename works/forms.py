from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import Pseud
from tags.services import check_tag_types, parse_tag_names

from .models import Chapter, PublicationStatus, Work, WorkAuthor
from .sanitize import autoparagraph, clean_html
from .services import TAG_FIELDS
from .text import count_words

MAX_TAGS = 75
MAX_SUMMARY = 2500
MAX_NOTES = 10000
MAX_CHAPTER = 510000


def clean_limited_html(value, limit):
    html = clean_html(autoparagraph(value))
    if len(html) > limit:
        raise ValidationError(_("Texto longo demais (máximo de %(max)d caracteres).") % {"max": limit})
    return html


class TagField(forms.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Separe as tags por vírgula."))
        super().__init__(*args, **kwargs)

    def clean(self, value):
        names = parse_tag_names(super().clean(value))
        if self.required and not names:
            raise ValidationError(self.error_messages["required"], code="required")
        return names


class PublishForm(forms.Form):
    ACTIONS = [("draft", _("Salvar rascunho")), ("publish", _("Publicar")), ("schedule", _("Agendar"))]

    action = forms.ChoiceField(choices=ACTIONS)
    scheduled_for = forms.DateTimeField(
        label=_("Publicar em"),
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    def clean(self):
        data = super().clean()
        if data.get("action") == "schedule":
            when = data.get("scheduled_for")
            if not when:
                self.add_error("scheduled_for", _("Escolha a data e a hora da publicação."))
            elif when <= timezone.now():
                self.add_error("scheduled_for", _("A data precisa estar no futuro."))
        return data


class WorkForm(forms.ModelForm):
    pseuds = forms.ModelMultipleChoiceField(
        label=_("Publicar como"), queryset=Pseud.objects.none(), widget=forms.CheckboxSelectMultiple
    )
    warnings = forms.MultipleChoiceField(
        label=_("Avisos"), choices=Work.Warning.choices, widget=forms.CheckboxSelectMultiple
    )
    categories = forms.MultipleChoiceField(
        label=_("Categorias"), choices=Work.Category.choices, widget=forms.CheckboxSelectMultiple, required=False
    )
    fandom_tags = TagField(label=_("Fandoms"))
    relationship_tags = TagField(label=_("Relacionamentos"), required=False)
    character_tags = TagField(label=_("Personagens"), required=False)
    freeform_tags = TagField(label=_("Tags livres"), required=False)

    class Meta:
        model = Work
        fields = [
            "title", "pseuds", "rating", "warnings", "categories", "fandom_tags", "relationship_tags",
            "character_tags", "freeform_tags", "language", "summary", "notes", "end_notes",
            "is_complete", "expected_chapters", "restricted",
        ]  # fmt: skip
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 4}),
            "end_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["pseuds"].queryset = user.pseuds.all()
        for field, tag_type in TAG_FIELDS.items():
            self.fields[field].widget.attrs.update(
                {"data-tag-autocomplete": tag_type, "data-tag-multiple": "1", "autocomplete": "off"}
            )
        if self.instance.pk:
            self.fields["pseuds"].initial = list(
                user.pseuds.filter(
                    authorships__work=self.instance, authorships__status=WorkAuthor.Status.ACCEPTED
                ).values_list("pk", flat=True)
            )
            tags = list(self.instance.tags.all())
            for field, tag_type in TAG_FIELDS.items():
                self.fields[field].initial = ", ".join(tag.name for tag in tags if tag.type == tag_type)
        else:
            default = user.default_pseud
            self.fields["pseuds"].initial = [default.pk] if default else []

    def clean_summary(self):
        return clean_limited_html(self.cleaned_data["summary"], MAX_SUMMARY)

    def clean_notes(self):
        return clean_limited_html(self.cleaned_data["notes"], MAX_NOTES)

    def clean_end_notes(self):
        return clean_limited_html(self.cleaned_data["end_notes"], MAX_NOTES)

    def clean(self):
        data = super().clean()
        total = 0
        for field, tag_type in TAG_FIELDS.items():
            names = data.get(field) or []
            total += len(names)
            try:
                check_tag_types(names, tag_type)
            except ValidationError as error:
                self.add_error(field, error)
        if total > MAX_TAGS:
            raise ValidationError(_("Use no máximo %(max)d tags.") % {"max": MAX_TAGS})
        return data


class ChapterForm(forms.ModelForm):
    class Meta:
        model = Chapter
        fields = ["title", "summary", "notes", "content", "end_notes"]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "end_notes": forms.Textarea(attrs={"rows": 3}),
            "content": forms.Textarea(attrs={"rows": 20, "data-editor": "1"}),
        }

    def __init__(self, *args, allow_images=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_images = allow_images

    def clean_summary(self):
        return clean_limited_html(self.cleaned_data["summary"], MAX_SUMMARY)

    def clean_notes(self):
        return clean_limited_html(self.cleaned_data["notes"], MAX_NOTES)

    def clean_end_notes(self):
        return clean_limited_html(self.cleaned_data["end_notes"], MAX_NOTES)

    def clean_content(self):
        html = clean_html(autoparagraph(self.cleaned_data["content"]), allow_images=self.allow_images)
        if len(html) > MAX_CHAPTER:
            raise ValidationError(_("Capítulo longo demais (máximo de %(max)d caracteres).") % {"max": MAX_CHAPTER})
        if count_words(html) == 0 and "<img" not in html:
            raise ValidationError(_("O capítulo não pode ficar vazio."))
        self.instance.word_count = count_words(html)
        return html


class CoauthorInviteForm(forms.Form):
    username = forms.CharField(label=_("Nome de usuário da pessoa"), max_length=150)

    def __init__(self, *args, work, **kwargs):
        super().__init__(*args, **kwargs)
        self.work = work

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        user = get_user_model().objects.filter(
            username__iexact=username, is_active=True, is_approved=True
        ).first()
        if user is None:
            raise ValidationError(_("Não encontramos uma conta ativa com esse nome."))
        if self.work.authorships.filter(pseud__user=user).exists():
            raise ValidationError(_("Essa pessoa já é autora ou já foi convidada."))
        self.pseud = user.default_pseud
        return username


def publish_actions(obj):
    # O que já foi publicado só pode ser salvo
    if obj is not None and obj.pk and obj.status == PublicationStatus.PUBLISHED:
        return []
    return PublishForm.ACTIONS
