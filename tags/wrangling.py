from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from moderation.models import ModerationAction
from moderation.services import log_action

from .models import MetaTagging, Tag
from .services import descendant_ids, filter_tag_ids

Action = ModerationAction.Action
WRANGLERS_GROUP = "Wranglers"


class WranglingError(Exception):
    pass


def _queue_for(*tags):
    # Obras que podem ter mudado de filtro: as da tag, sinônimos e subtags
    from works.listing import queue_refresh, works_with_tags

    tag_ids = set()
    for tag in tags:
        tag_ids |= filter_tag_ids(tag) | {tag.pk}
    queue_refresh(works_with_tags(tag_ids))


def can_wrangle(user):
    return user.is_authenticated and (user.is_staff or user.has_perm("tags.wrangle"))


def find_canonical(name, tag_type):
    # Aceita digitar um sinônimo: usa a canônica dele
    tag = Tag.objects.select_related("merger").filter(name__lower=name.strip().lower()).first()
    if tag is None:
        raise WranglingError(_("Tag “%(name)s” não encontrada.") % {"name": name.strip()})
    if tag.merger_id:
        tag = tag.merger
    if not tag.canonical:
        raise WranglingError(_("“%(name)s” não é canônica.") % {"name": tag.name})
    if tag.type != tag_type:
        raise WranglingError(
            _("“%(name)s” é do tipo %(type)s.") % {"name": tag.name, "type": tag.get_type_display()}
        )
    return tag


@transaction.atomic
def canonize(tag, actor):
    if tag.canonical:
        return False
    if tag.merger_id:
        raise WranglingError(_("“%(name)s” é sinônimo de outra tag; desfaça o sinônimo antes.") % {"name": tag.name})
    tag.canonical = True
    tag.save(update_fields=["canonical"])
    log_action(actor, Action.TAG_CANONIZE, tag, note=tag.name)
    _queue_for(tag)
    return True


@transaction.atomic
def decanonize(tag, actor):
    if not tag.canonical:
        return False
    linked = (
        tag.synonyms.exists()
        or MetaTagging.objects.filter(Q(meta=tag) | Q(sub=tag)).exists()
        or tag.fandom_children.exists()
    )
    if linked:
        raise WranglingError(
            _("“%(name)s” tem sinônimos, metatags, subtags ou tags ligadas; remova essas ligações antes.")
            % {"name": tag.name}
        )
    tag.canonical = False
    tag.save(update_fields=["canonical"])
    log_action(actor, Action.TAG_DECANONIZE, tag, note=tag.name)
    _queue_for(tag)
    return True


def _link_meta(meta, sub):
    # Só cria a ligação se não formar ciclo
    if meta.pk != sub.pk and meta.pk not in descendant_ids({sub.pk}):
        MetaTagging.objects.get_or_create(meta=meta, sub=sub)


@transaction.atomic
def make_synonym(tag, canonical, actor):
    if tag.pk == canonical.pk:
        raise WranglingError(_("Uma tag não pode ser sinônimo de si mesma."))
    if not canonical.canonical or canonical.type != tag.type:
        raise WranglingError(_("O sinônimo precisa apontar para uma tag canônica do mesmo tipo."))
    if tag.merger_id == canonical.pk:
        return False
    if tag.canonical:
        # A canônica antiga vira sinônimo: tudo o que estava nela passa para a nova
        Tag.objects.filter(merger=tag).update(merger=canonical)
        for tagging in MetaTagging.objects.filter(sub=tag).select_related("meta"):
            _link_meta(tagging.meta, canonical)
        for tagging in MetaTagging.objects.filter(meta=tag).select_related("sub"):
            _link_meta(canonical, tagging.sub)
        MetaTagging.objects.filter(Q(meta=tag) | Q(sub=tag)).delete()
        canonical.fandoms.add(*tag.fandoms.all())
        for child in tag.fandom_children.all():
            child.fandoms.add(canonical)
        tag.fandom_children.clear()
        tag.canonical = False
    tag.fandoms.clear()
    tag.merger = canonical
    tag.save(update_fields=["canonical", "merger"])
    log_action(actor, Action.TAG_MERGE, tag, note=f"{tag.name} → {canonical.name}")
    _queue_for(tag, canonical)
    return True


@transaction.atomic
def unmerge(tag, actor):
    if not tag.merger_id:
        return False
    old_tag = tag.merger
    old = old_tag.name
    tag.merger = None
    tag.save(update_fields=["merger"])
    log_action(actor, Action.TAG_UNMERGE, tag, note=f"{tag.name} ↛ {old}")
    _queue_for(tag, old_tag)
    return True


@transaction.atomic
def add_metatag(sub, meta, actor):
    if not (sub.canonical and meta.canonical):
        raise WranglingError(_("Metatag e subtag precisam ser canônicas."))
    if sub.type != meta.type:
        raise WranglingError(_("Metatag e subtag precisam ser do mesmo tipo."))
    if meta.pk in descendant_ids({sub.pk}):
        raise WranglingError(
            _("“%(meta)s” já está abaixo de “%(sub)s”; isso criaria um ciclo.") % {"meta": meta.name, "sub": sub.name}
        )
    _tagging, created = MetaTagging.objects.get_or_create(meta=meta, sub=sub)
    if created:
        log_action(actor, Action.TAG_ADD_META, sub, note=f"{meta.name} > {sub.name}")
        _queue_for(sub)
    return created


@transaction.atomic
def remove_metatag(sub, meta, actor):
    deleted, _details = MetaTagging.objects.filter(meta=meta, sub=sub).delete()
    if deleted:
        log_action(actor, Action.TAG_REMOVE_META, sub, note=f"{meta.name} > {sub.name}")
        _queue_for(sub)
    return bool(deleted)


@transaction.atomic
def add_fandom(tag, fandom, actor):
    if tag.type == Tag.Type.FANDOM:
        raise WranglingError(_("Um fandom não é ligado a outro fandom."))
    if tag.merger_id:
        raise WranglingError(_("“%(name)s” é sinônimo; ligue a tag canônica ao fandom.") % {"name": tag.name})
    if not (fandom.canonical and fandom.type == Tag.Type.FANDOM):
        raise WranglingError(_("“%(name)s” não é um fandom canônico.") % {"name": fandom.name})
    if tag.fandoms.filter(pk=fandom.pk).exists():
        return False
    tag.fandoms.add(fandom)
    log_action(actor, Action.TAG_ADD_FANDOM, tag, note=f"{tag.name} ∈ {fandom.name}")
    return True


@transaction.atomic
def remove_fandom(tag, fandom, actor):
    if not tag.fandoms.filter(pk=fandom.pk).exists():
        return False
    tag.fandoms.remove(fandom)
    log_action(actor, Action.TAG_REMOVE_FANDOM, tag, note=f"{tag.name} ∉ {fandom.name}")
    return True
