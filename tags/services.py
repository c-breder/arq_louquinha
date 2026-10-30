import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _

from .models import MetaTagging, Tag

MAX_TAG_LENGTH = 150


def parse_tag_names(raw):
    # "Angst,  fluff , Angst" -> ["Angst", "fluff"]
    names = []
    seen = set()
    for piece in (raw or "").split(","):
        name = re.sub(r"\s+", " ", piece).strip()
        if not name:
            continue
        if len(name) > MAX_TAG_LENGTH:
            raise ValidationError(
                _("A tag \"%(name)s…\" passa de %(max)d caracteres.") % {"name": name[:30], "max": MAX_TAG_LENGTH}
            )
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def check_tag_types(names, tag_type):
    # Só valida (usado no formulário); as tags novas são criadas ao salvar
    lowered = [name.lower() for name in names]
    for tag in Tag.objects.filter(name__lower__in=lowered).exclude(type=tag_type):
        raise ValidationError(
            _("A tag \"%(name)s\" já existe como %(type)s.") % {"name": tag.name, "type": tag.get_type_display()}
        )


def resolve_tags(names, tag_type):
    """Usa a tag existente (mesmo nome, ignorando maiúsculas) ou cria uma nova não canônica."""
    tags = []
    for name in names:
        tag = Tag.objects.filter(name__lower=name.lower()).first()
        if tag is None:
            try:
                with transaction.atomic():
                    tag = Tag.objects.create(name=name, type=tag_type)
            except IntegrityError:
                tag = Tag.objects.get(name__lower=name.lower())
        if tag.type != tag_type:
            raise ValidationError(
                _("A tag \"%(name)s\" já existe como %(type)s.") % {"name": tag.name, "type": tag.get_type_display()}
            )
        tags.append(tag)
    return tags


def _walk(tag_ids, source, target):
    # Percorre as metatags em largura (source -> target), sem repetir
    found = set(tag_ids)
    frontier = set(tag_ids)
    while frontier:
        step = set(
            MetaTagging.objects.filter(**{f"{source}_id__in": frontier}).values_list(f"{target}_id", flat=True)
        )
        frontier = step - found
        found |= frontier
    return found


def descendant_ids(tag_ids):
    """As tags e todas as subtags abaixo delas."""
    return _walk(tag_ids, "meta", "sub")


def ancestor_ids(tag_ids):
    """As tags e todas as metatags acima delas."""
    return _walk(tag_ids, "sub", "meta")


def filter_tag_ids(tag):
    """Ids das tags cujas obras aparecem ao filtrar por esta tag: canônica + subtags + sinônimos de todas."""
    base = tag.merger if tag.merger_id else tag
    if not base.canonical:
        return {tag.pk}
    canonical_ids = descendant_ids({base.pk})
    synonym_ids = set(Tag.objects.filter(merger_id__in=canonical_ids).values_list("pk", flat=True))
    return canonical_ids | synonym_ids


def work_filter_ids(tag_ids):
    """Tags pelas quais uma obra pode ser encontrada: as canônicas das tags dela e todas as metatags acima."""
    canonical_ids = set()
    for pk, canonical, merger_id in Tag.objects.filter(pk__in=tag_ids).values_list("pk", "canonical", "merger_id"):
        if merger_id:
            canonical_ids.add(merger_id)
        elif canonical:
            canonical_ids.add(pk)
    return ancestor_ids(canonical_ids)


def refresh_use_counts(tag_ids):
    if not tag_ids:
        return
    WorkTag = Tag.works.through
    uses = WorkTag.objects.filter(tag_id=OuterRef("pk")).values("tag_id").annotate(total=Count("*")).values("total")
    Tag.objects.filter(pk__in=tag_ids).update(use_count=Coalesce(Subquery(uses), 0))
