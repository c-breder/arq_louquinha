import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from tags.models import MetaTagging, Tag

pytestmark = pytest.mark.django_db


def test_tag_name_is_unique_ignoring_case():
    Tag.objects.create(name="Angst", type=Tag.Type.FREEFORM)
    with pytest.raises(IntegrityError):
        Tag.objects.create(name="angst", type=Tag.Type.FREEFORM)


def test_synonym_must_point_to_canonical_of_same_type():
    canonical = Tag.objects.create(name="Família Encontrada", type=Tag.Type.FREEFORM, canonical=True)
    synonym = Tag(name="Found Family", type=Tag.Type.FREEFORM, merger=canonical)
    synonym.full_clean()

    not_canonical = Tag.objects.create(name="algo", type=Tag.Type.FREEFORM)
    with pytest.raises(ValidationError):
        Tag(name="outro", type=Tag.Type.FREEFORM, merger=not_canonical).full_clean()

    character = Tag.objects.create(name="Ana", type=Tag.Type.CHARACTER, canonical=True)
    with pytest.raises(ValidationError):
        Tag(name="Aninha", type=Tag.Type.FREEFORM, merger=character).full_clean()


def test_canonical_tag_cannot_have_merger_in_database():
    canonical = Tag.objects.create(name="Fluff", type=Tag.Type.FREEFORM, canonical=True)
    with pytest.raises(IntegrityError):
        Tag.objects.create(name="Fofura", type=Tag.Type.FREEFORM, canonical=True, merger=canonical)


def test_metatagging_rules():
    meta = Tag.objects.create(name="Universo Alternativo", type=Tag.Type.FREEFORM, canonical=True)
    sub = Tag.objects.create(name="Coffee Shop AU", type=Tag.Type.FREEFORM, canonical=True)
    MetaTagging(meta=meta, sub=sub).full_clean()

    loose = Tag.objects.create(name="cafezinho", type=Tag.Type.FREEFORM)
    with pytest.raises(ValidationError):
        MetaTagging(meta=meta, sub=loose).full_clean()

    with pytest.raises(IntegrityError):
        MetaTagging.objects.create(meta=meta, sub=meta)
