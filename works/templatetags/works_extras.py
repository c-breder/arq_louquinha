from django import template
from django.utils.safestring import mark_safe

from works.models import WORK_LANGUAGES, Work
from works.sanitize import clean_html

register = template.Library()
LANGUAGE_NAMES = dict(WORK_LANGUAGES)


@register.filter
def rating_label(value):
    return Work.Rating(value).label if value in Work.Rating.values else value


@register.filter
def warning_labels(values):
    return [Work.Warning(value).label for value in values if value in Work.Warning.values]


@register.filter
def language_label(value):
    return LANGUAGE_NAMES.get(value, value)


@register.filter
def get_item(mapping, key):
    return mapping.get(key, []) if mapping else []


@register.filter
def of_type(tags, tag_type):
    # Usa a lista já carregada (prefetch), sem nova consulta
    return [tag for tag in tags if tag.type == tag_type]


@register.filter
def clean(value):
    # Filtra de novo na exibição (defesa extra caso algo antigo tenha escapado)
    return mark_safe(clean_html(value))
