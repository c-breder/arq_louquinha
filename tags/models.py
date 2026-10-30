from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class Tag(models.Model):
    class Type(models.TextChoices):
        FANDOM = "fandom", _("Fandom")
        RELATIONSHIP = "relationship", _("Relacionamento")
        CHARACTER = "character", _("Personagem")
        FREEFORM = "freeform", _("Tag livre")

    name = models.CharField(_("nome"), max_length=150)
    type = models.CharField(_("tipo"), max_length=20, choices=Type.choices)
    canonical = models.BooleanField(_("canônica"), default=False)
    # Sinônimo: aponta para a tag canônica
    merger = models.ForeignKey(
        "self",
        verbose_name=_("sinônimo de"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="synonyms",
    )
    # Personagens, relacionamentos e tags livres ligados a fandoms
    fandoms = models.ManyToManyField(
        "self",
        verbose_name=_("fandoms"),
        symmetrical=False,
        blank=True,
        related_name="fandom_children",
        limit_choices_to={"type": Type.FANDOM, "canonical": True},
    )
    use_count = models.PositiveIntegerField(_("usos"), default=0)
    created_at = models.DateTimeField(_("criada em"), auto_now_add=True)

    class Meta:
        verbose_name = _("tag")
        verbose_name_plural = _("tags")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="tag_name_unique_ci"),
            models.CheckConstraint(
                condition=models.Q(canonical=False) | models.Q(merger__isnull=True),
                name="tag_canonical_has_no_merger",
            ),
        ]
        indexes = [
            models.Index(fields=["type", "canonical"]),
        ]
        permissions = [("wrangle", _("Pode fazer wrangling de tags"))]

    def __str__(self):
        return self.name

    def clean(self):
        if self.merger_id is None:
            return
        if self.canonical:
            raise ValidationError({"merger": _("Uma tag canônica não pode ser sinônimo de outra.")})
        if self.merger_id == self.pk:
            raise ValidationError({"merger": _("Uma tag não pode ser sinônimo de si mesma.")})
        if not self.merger.canonical:
            raise ValidationError({"merger": _("O sinônimo precisa apontar para uma tag canônica.")})
        if self.merger.type != self.type:
            raise ValidationError({"merger": _("O sinônimo precisa ser do mesmo tipo da tag canônica.")})


class MetaTagging(models.Model):
    # Metatag (mais ampla) acima de uma subtag (mais específica)
    meta = models.ForeignKey(
        Tag, verbose_name=_("metatag"), on_delete=models.CASCADE, related_name="sub_taggings"
    )
    sub = models.ForeignKey(
        Tag, verbose_name=_("subtag"), on_delete=models.CASCADE, related_name="meta_taggings"
    )

    class Meta:
        verbose_name = _("metatag")
        verbose_name_plural = _("metatags")
        constraints = [
            models.UniqueConstraint(fields=["meta", "sub"], name="metatagging_unique"),
            models.CheckConstraint(condition=~models.Q(meta=models.F("sub")), name="metatagging_not_self"),
        ]

    def __str__(self):
        return f"{self.meta} > {self.sub}"

    def clean(self):
        if not (self.meta.canonical and self.sub.canonical):
            raise ValidationError(_("Metatag e subtag precisam ser canônicas."))
        if self.meta.type != self.sub.type:
            raise ValidationError(_("Metatag e subtag precisam ser do mesmo tipo."))
