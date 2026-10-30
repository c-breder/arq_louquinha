from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import Pseud
from tags.models import Tag

# Idioma da obra (não é o idioma da interface); nomes na própria língua
WORK_LANGUAGES = [
    ("pt-br", "Português (Brasil)"),
    ("pt", "Português"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("zh", "中文"),
    ("other", "Outro / Other"),
]


class PublicationStatus(models.TextChoices):
    DRAFT = "draft", _("Rascunho")
    SCHEDULED = "scheduled", _("Agendada")
    PUBLISHED = "published", _("Publicada")


class Work(models.Model):
    class Rating(models.TextChoices):
        GENERAL = "general", _("Público geral")
        TEEN = "teen", _("Adolescentes e acima")
        MATURE = "mature", _("Maduro")
        EXPLICIT = "explicit", _("Explícito")
        NOT_RATED = "not_rated", _("Sem classificação")

    class Warning(models.TextChoices):
        CHOSE_NOT_TO_WARN = "chose_not_to_warn", _("Autor optou por não usar avisos")
        VIOLENCE = "violence", _("Descrições gráficas de violência")
        MAJOR_CHARACTER_DEATH = "major_character_death", _("Morte de personagem principal")
        NONE_APPLY = "none_apply", _("Nenhum aviso se aplica")
        NON_CON = "non_con", _("Estupro/Não consensual")
        UNDERAGE = "underage", _("Sexo envolvendo menores")

    class Category(models.TextChoices):
        FF = "ff", "F/F"
        FM = "fm", "F/M"
        GEN = "gen", "Gen"
        MM = "mm", "M/M"
        MULTI = "multi", "Multi"
        OTHER = "other", _("Outra")

    title = models.CharField(_("título"), max_length=255)
    summary = models.TextField(_("resumo"), blank=True)
    notes = models.TextField(_("notas iniciais"), blank=True)
    end_notes = models.TextField(_("notas finais"), blank=True)
    language = models.CharField(_("idioma"), max_length=10, choices=WORK_LANGUAGES, default="pt-br")
    rating = models.CharField(_("classificação"), max_length=20, choices=Rating.choices)
    warnings = ArrayField(
        models.CharField(max_length=30, choices=Warning.choices),
        verbose_name=_("avisos"),
        default=list,
    )
    categories = ArrayField(
        models.CharField(max_length=10, choices=Category.choices),
        verbose_name=_("categorias"),
        default=list,
        blank=True,
    )
    tags = models.ManyToManyField(Tag, verbose_name=_("tags"), blank=True, related_name="works")
    pseuds = models.ManyToManyField(
        Pseud, verbose_name=_("autores"), through="WorkAuthor", related_name="works"
    )
    is_complete = models.BooleanField(_("completa"), default=False)
    expected_chapters = models.PositiveSmallIntegerField(_("capítulos previstos"), null=True, blank=True)
    restricted = models.BooleanField(_("só para usuários logados"), default=False)
    status = models.CharField(
        _("situação"), max_length=20, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT
    )
    scheduled_for = models.DateTimeField(_("publicar em"), null=True, blank=True)
    published_at = models.DateTimeField(_("publicada em"), null=True, blank=True)
    created_at = models.DateTimeField(_("criada em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizada em"), auto_now=True)
    word_count = models.PositiveIntegerField(_("palavras"), default=0)
    hit_count = models.PositiveBigIntegerField(_("acessos"), default=0)
    hidden_by_moderator = models.BooleanField(_("oculta pela moderação"), default=False)

    class Meta:
        verbose_name = _("obra")
        verbose_name_plural = _("obras")
        indexes = [
            models.Index(fields=["status", "-published_at"]),
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self):
        return self.title

    @property
    def authors(self):
        return Pseud.objects.filter(
            authorships__work=self, authorships__status=WorkAuthor.Status.ACCEPTED
        ).select_related("user")


class WorkAuthor(models.Model):
    # Coautoria: o convidado precisa aceitar
    class Status(models.TextChoices):
        PENDING = "pending", _("Convite pendente")
        ACCEPTED = "accepted", _("Aceito")

    work = models.ForeignKey(Work, verbose_name=_("obra"), on_delete=models.CASCADE, related_name="authorships")
    pseud = models.ForeignKey(
        Pseud, verbose_name=_("pseudônimo"), on_delete=models.CASCADE, related_name="authorships"
    )
    status = models.CharField(_("situação"), max_length=10, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("convidado por"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("autoria")
        verbose_name_plural = _("autorias")
        constraints = [
            models.UniqueConstraint(fields=["work", "pseud"], name="workauthor_unique"),
        ]

    def __str__(self):
        return f"{self.pseud} – {self.work}"


class Chapter(models.Model):
    work = models.ForeignKey(Work, verbose_name=_("obra"), on_delete=models.CASCADE, related_name="chapters")
    position = models.PositiveSmallIntegerField(_("posição"))
    title = models.CharField(_("título"), max_length=255, blank=True)
    summary = models.TextField(_("resumo"), blank=True)
    notes = models.TextField(_("notas iniciais"), blank=True)
    end_notes = models.TextField(_("notas finais"), blank=True)
    content = models.TextField(_("texto"))
    word_count = models.PositiveIntegerField(_("palavras"), default=0)
    status = models.CharField(
        _("situação"), max_length=20, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT
    )
    scheduled_for = models.DateTimeField(_("publicar em"), null=True, blank=True)
    published_at = models.DateTimeField(_("publicado em"), null=True, blank=True)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("capítulo")
        verbose_name_plural = _("capítulos")
        ordering = ["work", "position"]
        constraints = [
            models.UniqueConstraint(fields=["work", "position"], name="chapter_position_unique"),
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self):
        return self.title or _("Capítulo %(number)s") % {"number": self.position}


class Series(models.Model):
    title = models.CharField(_("título"), max_length=255)
    summary = models.TextField(_("resumo"), blank=True)
    notes = models.TextField(_("notas"), blank=True)
    is_complete = models.BooleanField(_("completa"), default=False)
    pseuds = models.ManyToManyField(Pseud, verbose_name=_("autores"), related_name="series")
    works = models.ManyToManyField(Work, verbose_name=_("obras"), through="SeriesWork", related_name="series")
    created_at = models.DateTimeField(_("criada em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizada em"), auto_now=True)

    class Meta:
        verbose_name = _("série")
        verbose_name_plural = _("séries")

    def __str__(self):
        return self.title


class WorkListing(models.Model):
    """Cópia achatada da obra para listagens e busca (uma linha, sem joins). Atualizada pelo Celery."""

    work = models.OneToOneField(Work, primary_key=True, on_delete=models.CASCADE, related_name="listing")
    visible = models.BooleanField(default=False)
    restricted = models.BooleanField(default=False)
    title = models.CharField(max_length=255)
    rating = models.CharField(max_length=20)
    warnings = ArrayField(models.CharField(max_length=30), default=list)
    categories = ArrayField(models.CharField(max_length=10), default=list)
    language = models.CharField(max_length=10)
    is_complete = models.BooleanField(default=False)
    word_count = models.PositiveIntegerField(default=0)
    chapter_count = models.PositiveSmallIntegerField(default=0)
    expected_chapters = models.PositiveSmallIntegerField(null=True)
    published_at = models.DateTimeField(null=True)
    revised_at = models.DateTimeField(null=True)
    kudos_count = models.PositiveIntegerField(default=0)
    hit_count = models.PositiveBigIntegerField(default=0)
    bookmark_count = models.PositiveIntegerField(default=0)
    comment_count = models.PositiveIntegerField(default=0)
    # Canônicas das tags + metatags acima + tags ainda não organizadas
    filter_ids = ArrayField(models.BigIntegerField(), default=list)
    card = models.JSONField(default=dict)
    authors_text = models.TextField(blank=True)
    tags_text = models.TextField(blank=True)
    summary_text = models.TextField(blank=True)
    search_vector = SearchVectorField(null=True)
    # Muda a cada atualização; faz parte da chave do cache do card
    refreshed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            GinIndex(fields=["filter_ids"], name="listing_filter_ids_gin"),
            GinIndex(fields=["search_vector"], name="listing_search_gin"),
            models.Index(fields=["visible", "-revised_at"], name="listing_revised_idx"),
            models.Index(fields=["visible", "-published_at"], name="listing_published_idx"),
            models.Index(fields=["visible", "-kudos_count"], name="listing_kudos_idx"),
            models.Index(fields=["visible", "-hit_count"], name="listing_hits_idx"),
            models.Index(fields=["visible", "-word_count"], name="listing_words_idx"),
            models.Index(fields=["visible", "language"], name="listing_language_idx"),
        ]

    def __str__(self):
        return self.title


def work_image_path(instance, filename):
    return f"imagens/{instance.owner_id}/{filename}"


class WorkImage(models.Model):
    # Imagem enviada para dentro do texto (já convertida para WebP)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("dono"), on_delete=models.CASCADE, related_name="work_images"
    )
    file = models.ImageField(_("arquivo"), upload_to=work_image_path)
    width = models.PositiveIntegerField(_("largura"), default=0)
    height = models.PositiveIntegerField(_("altura"), default=0)
    size = models.PositiveIntegerField(_("tamanho em bytes"), default=0)
    created_at = models.DateTimeField(_("enviada em"), auto_now_add=True)

    class Meta:
        verbose_name = _("imagem")
        verbose_name_plural = _("imagens")

    def __str__(self):
        return self.file.name


class SeriesWork(models.Model):
    series = models.ForeignKey(Series, verbose_name=_("série"), on_delete=models.CASCADE, related_name="entries")
    work = models.ForeignKey(Work, verbose_name=_("obra"), on_delete=models.CASCADE, related_name="series_entries")
    position = models.PositiveSmallIntegerField(_("posição"))

    class Meta:
        verbose_name = _("obra na série")
        verbose_name_plural = _("obras na série")
        ordering = ["series", "position"]
        constraints = [
            models.UniqueConstraint(fields=["series", "work"], name="serieswork_unique"),
        ]

    def __str__(self):
        return f"{self.series} #{self.position}"
