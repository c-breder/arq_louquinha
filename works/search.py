from datetime import datetime, time

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tags.models import Tag
from tags.services import parse_tag_names

from .listing import apply_text_search, base_listings, tag_filter_id
from .models import WORK_LANGUAGES, Work

SORTS = {
    "relevancia": ("-rank", "-revised_at"),
    "atualizadas": ("-revised_at",),
    "publicadas": ("-published_at",),
    "kudos": ("-kudos_count", "-revised_at"),
    "acessos": ("-hit_count", "-revised_at"),
    "bookmarks": ("-bookmark_count", "-revised_at"),
    "comentarios": ("-comment_count", "-revised_at"),
    "palavras": ("-word_count",),
    "titulo": ("title",),
}
SORT_CHOICES = [
    ("atualizadas", _("Atualização mais recente")),
    ("publicadas", _("Publicação mais recente")),
    ("relevancia", _("Relevância (busca por texto)")),
    ("kudos", _("Mais kudos")),
    ("acessos", _("Mais acessos")),
    ("bookmarks", _("Mais bookmarks")),
    ("comentarios", _("Mais comentários")),
    ("palavras", _("Mais palavras")),
    ("titulo", _("Título (A–Z)")),
]


class WorkSearchForm(forms.Form):
    # Os nomes dos campos aparecem na URL, por isso estão em português
    q = forms.CharField(label=_("Texto"), required=False, max_length=200)
    incluir = forms.CharField(label=_("Com as tags"), required=False, help_text=_("Separe por vírgula."))
    excluir = forms.CharField(label=_("Sem as tags"), required=False)
    classificacao = forms.MultipleChoiceField(
        label=_("Classificação"), choices=Work.Rating.choices, required=False, widget=forms.CheckboxSelectMultiple
    )
    avisos = forms.MultipleChoiceField(
        label=_("Com os avisos"), choices=Work.Warning.choices, required=False, widget=forms.CheckboxSelectMultiple
    )
    categorias = forms.MultipleChoiceField(
        label=_("Categorias"), choices=Work.Category.choices, required=False, widget=forms.CheckboxSelectMultiple
    )
    idioma = forms.ChoiceField(label=_("Idioma"), choices=[("", _("Qualquer"))] + WORK_LANGUAGES, required=False)
    completa = forms.ChoiceField(
        label=_("Situação"),
        choices=[("", _("Qualquer")), ("sim", _("Completas")), ("nao", _("Em andamento"))],
        required=False,
    )
    palavras_min = forms.IntegerField(label=_("Palavras (mínimo)"), required=False, min_value=0)
    palavras_max = forms.IntegerField(label=_("Palavras (máximo)"), required=False, min_value=0)
    desde = forms.DateField(
        label=_("Atualizada desde"), required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    ate = forms.DateField(label=_("Atualizada até"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    ordenar = forms.ChoiceField(label=_("Ordenar por"), choices=SORT_CHOICES, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("incluir", "excluir"):
            self.fields[name].widget.attrs.update(
                {"data-tag-autocomplete": "", "data-tag-multiple": "1", "autocomplete": "off"}
            )

    def _resolve(self, field):
        tags, unknown = [], []
        for name in parse_tag_names(self.cleaned_data.get(field)):
            tag = Tag.objects.filter(name__lower=name.lower()).first()
            if tag is None:
                unknown.append(name)
            else:
                tags.append(tag)
        if unknown:
            self.add_error(field, _("Tags não encontradas: %(names)s") % {"names": ", ".join(unknown)})
        return tags

    def clean(self):
        data = super().clean()
        data["include_tags"] = self._resolve("incluir")
        data["exclude_tags"] = self._resolve("excluir")
        return data


def search(user, form):
    """Aplica os filtros do formulário (já validado) sobre a tabela de listagens."""
    data = form.cleaned_data
    listings = base_listings(user)
    text = data.get("q", "").strip()
    sort = data.get("ordenar") or ("relevancia" if text else "atualizadas")
    if text:
        listings = apply_text_search(listings, text, rank=sort == "relevancia")
    if sort == "relevancia" and not text:
        sort = "atualizadas"

    for tag in data["include_tags"]:
        listings = listings.filter(filter_ids__contains=[tag_filter_id(tag)])
    if data["exclude_tags"]:
        listings = listings.exclude(filter_ids__overlap=[tag_filter_id(tag) for tag in data["exclude_tags"]])
    if data.get("classificacao"):
        listings = listings.filter(rating__in=data["classificacao"])
    if data.get("avisos"):
        listings = listings.filter(warnings__contains=data["avisos"])
    if data.get("categorias"):
        listings = listings.filter(categories__overlap=data["categorias"])
    if data.get("idioma"):
        listings = listings.filter(language=data["idioma"])
    if data.get("completa"):
        listings = listings.filter(is_complete=data["completa"] == "sim")
    if data.get("palavras_min") is not None:
        listings = listings.filter(word_count__gte=data["palavras_min"])
    if data.get("palavras_max") is not None:
        listings = listings.filter(word_count__lte=data["palavras_max"])
    tz = timezone.get_current_timezone()
    if data.get("desde"):
        listings = listings.filter(revised_at__gte=datetime.combine(data["desde"], time.min, tz))
    if data.get("ate"):
        listings = listings.filter(revised_at__lte=datetime.combine(data["ate"], time.max, tz))
    return listings.order_by(*SORTS[sort])
