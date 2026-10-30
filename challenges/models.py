from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from works.models import Work


class Collection(models.Model):
    class Kind(models.TextChoices):
        COLLECTION = "collection", _("Coleção")
        PROMPT_MEME = "prompt_meme", _("Desafio de prompts")

    slug = models.SlugField(_("endereço"), max_length=60, unique=True)
    title = models.CharField(_("título"), max_length=255)
    description = models.TextField(_("descrição"), blank=True)
    kind = models.CharField(_("tipo"), max_length=20, choices=Kind.choices, default=Kind.COLLECTION)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("dono"), on_delete=models.CASCADE, related_name="owned_collections"
    )
    moderators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_("moderadores"), blank=True, related_name="moderated_collections"
    )
    is_open = models.BooleanField(_("aceitando obras"), default=True)
    is_moderated = models.BooleanField(_("obras precisam de aprovação"), default=False)
    closes_at = models.DateTimeField(_("prazo"), null=True, blank=True)
    created_at = models.DateTimeField(_("criada em"), auto_now_add=True)

    class Meta:
        verbose_name = _("coleção")
        verbose_name_plural = _("coleções")
        ordering = ["title"]

    def __str__(self):
        return self.title

    @property
    def accepting(self):
        return self.is_open and (self.closes_at is None or timezone.now() < self.closes_at)

    def can_manage(self, user):
        if not user.is_authenticated:
            return False
        return user.is_staff or self.owner_id == user.pk or self.moderators.filter(pk=user.pk).exists()


class Prompt(models.Model):
    collection = models.ForeignKey(
        Collection, verbose_name=_("coleção"), on_delete=models.CASCADE, related_name="prompts"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("autor"), null=True, on_delete=models.SET_NULL, related_name="+"
    )
    text = models.TextField(_("prompt"))
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("prompt")
        verbose_name_plural = _("prompts")
        ordering = ["created_at"]

    def __str__(self):
        return self.text[:60]


class CollectionItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Aguardando aprovação")
        APPROVED = "approved", _("Aprovada")
        REJECTED = "rejected", _("Recusada")

    collection = models.ForeignKey(Collection, verbose_name=_("coleção"), on_delete=models.CASCADE, related_name="items")
    work = models.ForeignKey(Work, verbose_name=_("obra"), on_delete=models.CASCADE, related_name="collection_items")
    prompt = models.ForeignKey(
        Prompt, verbose_name=_("responde ao prompt"), null=True, blank=True, on_delete=models.SET_NULL,
        related_name="fills",
    )
    status = models.CharField(_("situação"), max_length=10, choices=Status.choices, default=Status.PENDING)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(_("enviada em"), auto_now_add=True)

    class Meta:
        verbose_name = _("obra na coleção")
        verbose_name_plural = _("obras nas coleções")
        constraints = [models.UniqueConstraint(fields=["collection", "work"], name="collectionitem_unique")]
        indexes = [models.Index(fields=["collection", "status"])]

    def __str__(self):
        return f"{self.work} @ {self.collection}"
