from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from tags.models import Tag
from tags.services import check_tag_types, parse_tag_names, resolve_tags
from works.sanitize import autoparagraph, clean_html

from .models import Bookmark, Comment

MAX_COMMENT = 10000


class CommentForm(forms.ModelForm):
    parent = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Comment
        fields = ["pseud", "content"]
        labels = {"pseud": _("Comentar como"), "content": _("Comentário")}
        widgets = {"content": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["pseud"].queryset = user.pseuds.all()
        self.fields["pseud"].empty_label = None
        self.fields["pseud"].initial = user.default_pseud
        self.fields["pseud"].required = False  # sem escolha, usa o padrão
        if self.instance.pk:
            del self.fields["pseud"]

    def clean_pseud(self):
        return self.cleaned_data.get("pseud") or self.user.default_pseud

    def clean_content(self):
        html = clean_html(autoparagraph(self.cleaned_data["content"]))
        if len(html) > MAX_COMMENT:
            raise ValidationError(_("Comentário longo demais."))
        if not html.strip():
            raise ValidationError(_("Escreva alguma coisa."))
        return html


class BookmarkForm(forms.ModelForm):
    tag_names = forms.CharField(label=_("Suas tags"), required=False, help_text=_("Separe por vírgula."))

    class Meta:
        model = Bookmark
        fields = ["pseud", "notes", "tag_names", "is_rec", "is_private"]
        labels = {"pseud": _("Salvar como"), "notes": _("Notas")}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pseud"].queryset = user.pseuds.all()
        self.fields["pseud"].empty_label = None
        self.fields["tag_names"].widget.attrs.update(
            {"data-tag-autocomplete": Tag.Type.FREEFORM, "data-tag-multiple": "1", "autocomplete": "off"}
        )
        if self.instance.pk:
            self.fields["tag_names"].initial = ", ".join(tag.name for tag in self.instance.tags.all())
        else:
            self.fields["pseud"].initial = user.default_pseud

    def clean_notes(self):
        return clean_html(autoparagraph(self.cleaned_data["notes"]))

    def clean_tag_names(self):
        names = parse_tag_names(self.cleaned_data["tag_names"])
        check_tag_types(names, Tag.Type.FREEFORM)
        return names

    def save_tags(self, bookmark):
        # Só depois que o bookmark já existe no banco
        bookmark.tags.set(resolve_tags(self.cleaned_data["tag_names"], Tag.Type.FREEFORM))
