import random
import time
from collections import defaultdict
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from faker import Faker

from accounts.models import Pseud
from interactions.models import Bookmark, Comment, Kudos
from tags.models import MetaTagging, Tag
from works.listing import rebuild_all
from works.models import Chapter, PublicationStatus, Series, SeriesWork, Work, WorkAuthor
from works.text import count_words

SEED_EMAIL_DOMAIN = "seed.invalid"
SEED_PASSWORD = "senha-de-teste-123"
BATCH = 1000

# Tag canônica -> sinônimo comum (None = sem sinônimo)
FREEFORM_TROPES = {
    "Angst": None,
    "Fluff": None,
    "Slow Burn": None,
    "Hurt/Comfort": None,
    "Pining": None,
    "Romance": None,
    "Humor": None,
    "Drama": None,
    "Crack": None,
    "Drabble": None,
    "Halloween": None,
    "Família Encontrada": "Found Family",
    "Inimigos para Amantes": "Enemies to Lovers",
    "Amigos para Amantes": "Friends to Lovers",
    "Almas Gêmeas": "Soulmates",
    "Final Feliz": "Happy Ending",
    "Universo Alternativo": "Alternate Universe",
    "Universo Alternativo - Cafeteria": "Coffee Shop AU",
    "Universo Alternativo - Escola": "High School AU",
    "Universo Alternativo - Moderno": "Modern AU",
    "Universo Alternativo - Fantasia": "Fantasy AU",
    "Viagem no Tempo": "Time Travel",
    "Mistério": "Mystery",
    "Aventura": "Adventure",
    "Primeiro Beijo": "First Kiss",
    "Namoro de Mentira": "Fake Dating",
    "Só Tem Uma Cama": "There Was Only One Bed",
    "Pós-Canon": "Post-Canon",
    "Pré-Canon": "Pre-Canon",
    "Canon Divergente": "Canon Divergence",
    "Morte de Personagem": "Character Death",
    "Recuperação": "Recovery",
    "Natal": "Christmas",
    "Domesticidade": "Domestic Fluff",
    "Ciúmes": "Jealousy",
    "Reencontro": "Reunion",
}
METATAGS = {
    "Universo Alternativo": [
        "Universo Alternativo - Cafeteria",
        "Universo Alternativo - Escola",
        "Universo Alternativo - Moderno",
        "Universo Alternativo - Fantasia",
    ],
    "Romance": ["Slow Burn", "Primeiro Beijo", "Namoro de Mentira", "Pining"],
}
FANDOM_PATTERNS = [
    "Crônicas de {city}",
    "A Saga de {first}",
    "{last} Academy",
    "O Reino de {city}",
    "Os Herdeiros de {last}",
    "{city} Chronicles",
    "Lendas de {city}",
    "Projeto {last}",
]
FREEFORM_PATTERNS = [
    "{w1} {w2}",
    "{w1} e {w2}",
    "{w1} AU",
    "muito {w1}",
    "{first} merece ser feliz",
    "{w1} {w2} {w3}",
]


class Command(BaseCommand):
    help = "Popula o banco com dados falsos realistas (só para desenvolvimento)."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=200)
        parser.add_argument("--fandoms", type=int, default=25)
        parser.add_argument("--freeforms", type=int, default=300, help="tags livres geradas além dos tropos")
        parser.add_argument("--works", type=int, default=3000)
        parser.add_argument("--seed", type=int, default=42, help="semente aleatória (mesmo número = mesmos dados)")
        parser.add_argument("--clear", action="store_true", help="apaga os dados do seed anterior antes")
        parser.add_argument("--force", action="store_true", help="permite rodar com DEBUG desligado")

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("O seed só roda em desenvolvimento (use --force se tiver certeza).")
        if opts["users"] < 2:
            raise CommandError("Use pelo menos 2 usuários.")

        self.rng = random.Random(opts["seed"])
        Faker.seed(opts["seed"])
        self.fake = Faker(["pt_BR", "en_US"])
        self.now = timezone.now()
        start = time.monotonic()

        with transaction.atomic():
            if opts["clear"]:
                self.clear()
            self.used_tag_names = {name.lower() for name in Tag.objects.values_list("name", flat=True)}
            users, pseuds = self.create_users(opts["users"])
            fandoms = self.create_fandom_tags(opts["fandoms"])
            freeforms = self.create_freeforms(opts["freeforms"])
            works, main_pseud = self.create_works(opts["works"], pseuds, fandoms, freeforms)
            self.create_series(works, main_pseud)
            self.create_interactions(works, users, pseuds, freeforms)
            self.update_tag_counts()

        listed = rebuild_all()
        self.log(f"Listagens reconstruídas: {listed} obras.")
        self.stdout.write(self.style.SUCCESS(f"Seed concluído em {time.monotonic() - start:.1f}s."))

    def log(self, message):
        self.stdout.write(f"  {message}")

    # --- Limpeza ---

    def clear(self):
        User = get_user_model()
        seed_users = User.objects.filter(email__endswith=f"@{SEED_EMAIL_DOMAIN}")
        seed_works = WorkAuthor.objects.filter(pseud__user__in=seed_users).values("work_id")
        Series.objects.filter(pseuds__user__in=seed_users).delete()
        Work.objects.filter(pk__in=seed_works).delete()
        deleted_users = seed_users.delete()[1].get(User._meta.label, 0)
        deleted_tags = Tag.objects.filter(works__isnull=True, bookmarks__isnull=True).delete()[1].get(
            Tag._meta.label, 0
        )
        self.log(f"Apagados: {deleted_users} usuários do seed e {deleted_tags} tags sem uso.")

    # --- Utilitários ---

    def past_date(self, max_days):
        return self.now - timedelta(seconds=self.rng.randint(0, max_days * 86400))

    def new_tag(self, name, tag_type, canonical=True, allow_suffix=True):
        name = name.strip()[:140]
        if name.lower() in self.used_tag_names:
            if not allow_suffix:
                return None
            number = 2
            while f"{name} ({number})".lower() in self.used_tag_names:
                number += 1
            name = f"{name} ({number})"
        self.used_tag_names.add(name.lower())
        return Tag(name=name, type=tag_type, canonical=canonical)

    def make_synonyms(self, tags, namer, ratio):
        synonyms = []
        for tag in tags:
            if self.rng.random() < ratio:
                synonym = self.new_tag(namer(tag), tag.type, canonical=False, allow_suffix=False)
                if synonym:
                    synonym.merger = tag
                    synonyms.append(synonym)
        return Tag.objects.bulk_create(synonyms, batch_size=BATCH)

    def paragraphs(self, low, high):
        return "".join(
            f"<p>{self.fake.paragraph(nb_sentences=self.rng.randint(3, 8))}</p>"
            for _ in range(self.rng.randint(low, high))
        )

    # --- Usuários ---

    def create_users(self, count):
        User = get_user_model()
        password = make_password(SEED_PASSWORD)
        existing = set(User.objects.values_list("username", flat=True))
        users = []
        for _ in range(count):
            base = self.fake.user_name()[:40]
            username = base
            while username in existing:
                username = f"{base}{self.rng.randint(10, 99999)}"
            existing.add(username)
            users.append(
                User(
                    username=username,
                    email=f"{username}@{SEED_EMAIL_DOMAIN}",
                    password=password,
                    is_approved=True,
                    approved_at=self.now,
                    adult_confirmed_at=self.now,
                    date_joined=self.past_date(3 * 365),
                    media_level=self.rng.choices(list(User.MediaLevel.values), weights=[85, 15])[0],
                    language=self.rng.choices(["pt-br", "en"], weights=[85, 15])[0],
                )
            )
        users = User.objects.bulk_create(users, batch_size=BATCH)
        EmailAddress.objects.bulk_create(
            [EmailAddress(user=user, email=user.email, verified=True, primary=True) for user in users],
            batch_size=BATCH,
        )
        # bulk_create não dispara o sinal que cria o pseudônimo padrão
        pseuds = [Pseud(user=user, name=user.username, is_default=True) for user in users]
        for user in self.rng.sample(users, k=len(users) // 5):
            name = self.fake.first_name()
            if name.lower() != user.username.lower():
                pseuds.append(Pseud(user=user, name=name))
        pseuds = Pseud.objects.bulk_create(pseuds, batch_size=BATCH)
        self.log(f"{len(users)} usuários e {len(pseuds)} pseudônimos (senha: {SEED_PASSWORD}).")
        return users, pseuds

    # --- Tags ---

    def fandom_name(self):
        pattern = self.rng.choice(FANDOM_PATTERNS)
        return pattern.format(city=self.fake.city(), first=self.fake.first_name(), last=self.fake.last_name())

    def create_fandom_tags(self, count):
        T = Tag.Type
        fandoms = Tag.objects.bulk_create([self.new_tag(self.fandom_name(), T.FANDOM) for _ in range(count)])

        characters_by_fandom = {}
        characters = []
        for fandom in fandoms:
            group = [self.new_tag(self.fake.name(), T.CHARACTER) for _ in range(self.rng.randint(8, 20))]
            characters_by_fandom[fandom.pk] = group
            characters.extend(group)
        Tag.objects.bulk_create(characters, batch_size=BATCH)
        character_synonyms = self.make_synonyms(characters, lambda tag: tag.name.split()[0], 0.3)

        relationships_by_fandom = {}
        relationships = []
        for fandom in fandoms:
            group = []
            for _ in range(self.rng.randint(5, 15)):
                first, second = self.rng.sample(characters_by_fandom[fandom.pk], 2)
                separator = "/" if self.rng.random() < 0.75 else " & "
                tag = self.new_tag(f"{first.name}{separator}{second.name}", T.RELATIONSHIP, allow_suffix=False)
                if tag:
                    group.append(tag)
            relationships_by_fandom[fandom.pk] = group
            relationships.extend(group)
        Tag.objects.bulk_create(relationships, batch_size=BATCH)

        def reversed_pair(tag):
            separator = "/" if "/" in tag.name else " & "
            return separator.join(reversed(tag.name.split(separator, 1)))

        relationship_synonyms = self.make_synonyms(relationships, reversed_pair, 0.25)

        FandomLink = Tag.fandoms.through
        FandomLink.objects.bulk_create(
            [
                FandomLink(from_tag_id=tag.pk, to_tag_id=fandom.pk)
                for fandom in fandoms
                for tag in characters_by_fandom[fandom.pk] + relationships_by_fandom[fandom.pk]
            ],
            batch_size=BATCH,
        )

        # Nas obras, as pessoas usam tanto a canônica quanto os sinônimos
        synonyms_of = defaultdict(list)
        for synonym in character_synonyms + relationship_synonyms:
            synonyms_of[synonym.merger_id].append(synonym)

        def with_synonyms(tags):
            return [variant for tag in tags for variant in [tag, *synonyms_of[tag.pk]]]

        self.log(
            f"{len(fandoms)} fandoms, {len(characters) + len(character_synonyms)} personagens, "
            f"{len(relationships) + len(relationship_synonyms)} relacionamentos."
        )
        return [
            {
                "fandom": fandom,
                "characters": with_synonyms(characters_by_fandom[fandom.pk]),
                "relationships": with_synonyms(relationships_by_fandom[fandom.pk]),
            }
            for fandom in fandoms
        ]

    def freeform_name(self):
        pattern = self.rng.choice(FREEFORM_PATTERNS)
        return pattern.format(
            w1=self.fake.word().capitalize(), w2=self.fake.word(), w3=self.fake.word(), first=self.fake.first_name()
        )

    def create_freeforms(self, count):
        T = Tag.Type.FREEFORM
        tropes = [tag for tag in (self.new_tag(name, T, allow_suffix=False) for name in FREEFORM_TROPES) if tag]
        generated = [
            tag
            for tag in (
                self.new_tag(self.freeform_name(), T, canonical=self.rng.random() < 0.3, allow_suffix=False)
                for _ in range(count)
            )
            if tag
        ]
        Tag.objects.bulk_create(tropes + generated, batch_size=BATCH)

        by_name = {tag.name: tag for tag in tropes}
        synonyms = []
        for name, synonym_name in FREEFORM_TROPES.items():
            if synonym_name and name in by_name:
                synonym = self.new_tag(synonym_name, T, canonical=False, allow_suffix=False)
                if synonym:
                    synonym.merger = by_name[name]
                    synonyms.append(synonym)

        # Parte das tags geradas vira sinônimo de outra gerada canônica
        generated_canonical = [tag for tag in generated if tag.canonical]
        merged = []
        for tag in generated:
            if not tag.canonical and generated_canonical and self.rng.random() < 0.2:
                tag.merger = self.rng.choice(generated_canonical)
                merged.append(tag)
        Tag.objects.bulk_update(merged, ["merger"], batch_size=BATCH)
        Tag.objects.bulk_create(synonyms, batch_size=BATCH)

        MetaTagging.objects.bulk_create(
            [
                MetaTagging(meta=by_name[meta], sub=by_name[sub])
                for meta, subs in METATAGS.items()
                if meta in by_name
                for sub in subs
                if sub in by_name
            ]
        )

        # Tags populares aparecem mais (distribuição de cauda longa)
        pool = tropes + synonyms + generated
        self.freeform_weights = [1 / (index + 1) for index in range(len(pool))]
        self.log(f"{len(pool)} tags livres ({len(synonyms) + len(merged)} sinônimos).")
        return pool

    # --- Obras ---

    def pick_warnings(self):
        roll = self.rng.random()
        if roll < 0.45:
            return [Work.Warning.NONE_APPLY]
        if roll < 0.7:
            return [Work.Warning.CHOSE_NOT_TO_WARN]
        pool = [Work.Warning.VIOLENCE, Work.Warning.MAJOR_CHARACTER_DEATH]
        return self.rng.sample(pool, k=self.rng.choice([1, 1, 2]))

    def pick_tag_ids(self, fandoms, freeforms):
        rng = self.rng
        tag_ids = set()
        if fandoms:
            for group in rng.sample(fandoms, k=1 if rng.random() < 0.85 or len(fandoms) == 1 else 2):
                tag_ids.add(group["fandom"].pk)
                characters = group["characters"]
                tag_ids.update(tag.pk for tag in rng.sample(characters, k=min(len(characters), rng.randint(1, 5))))
                relationships = group["relationships"]
                if relationships and rng.random() < 0.8:
                    tag_ids.update(
                        tag.pk for tag in rng.sample(relationships, k=min(len(relationships), rng.randint(1, 3)))
                    )
        if freeforms:
            tag_ids.update(tag.pk for tag in rng.choices(freeforms, weights=self.freeform_weights, k=rng.randint(2, 10)))
        return tag_ids

    def create_works(self, count, pseuds, fandoms, freeforms):
        rng = self.rng
        works = []
        chapter_counts = []
        for _ in range(count):
            published = rng.random() < 0.95
            chapters = 1 if rng.random() < 0.55 else rng.randint(2, 12)
            complete = chapters == 1 or rng.random() < 0.5
            works.append(
                Work(
                    title=self.fake.sentence(nb_words=rng.randint(2, 6)).rstrip("."),
                    summary=f"<p>{self.fake.paragraph(nb_sentences=rng.randint(2, 4))}</p>",
                    notes=f"<p>{self.fake.sentence()}</p>" if rng.random() < 0.3 else "",
                    language=rng.choices(["pt-br", "en", "es", "pt"], weights=[70, 22, 5, 3])[0],
                    rating=rng.choices(Work.Rating.values, weights=[30, 30, 15, 15, 10])[0],
                    warnings=self.pick_warnings(),
                    categories=rng.sample(Work.Category.values, k=rng.choice([1, 1, 1, 2])),
                    is_complete=complete,
                    expected_chapters=chapters if complete else rng.choice([None, chapters + rng.randint(1, 5)]),
                    restricted=rng.random() < 0.1,
                    status=PublicationStatus.PUBLISHED if published else PublicationStatus.DRAFT,
                    published_at=self.past_date(3 * 365) if published else None,
                    hit_count=rng.randint(0, 5000) if published else 0,
                )
            )
            chapter_counts.append(chapters)
        works = Work.objects.bulk_create(works, batch_size=BATCH)

        authorships = []
        main_pseud = {}
        for work in works:
            pseud = rng.choice(pseuds)
            main_pseud[work.pk] = pseud
            authorships.append(WorkAuthor(work=work, pseud=pseud, status=WorkAuthor.Status.ACCEPTED))
            if rng.random() < 0.05:
                coauthor = rng.choice(pseuds)
                if coauthor.user_id != pseud.user_id:
                    authorships.append(WorkAuthor(work=work, pseud=coauthor, status=WorkAuthor.Status.ACCEPTED))
        WorkAuthor.objects.bulk_create(authorships, batch_size=BATCH)

        WorkTag = Work.tags.through
        work_tags = []
        chapters = []
        total_chapters = 0
        for work, chapter_count in zip(works, chapter_counts):
            work_tags.extend(WorkTag(work_id=work.pk, tag_id=tag_id) for tag_id in self.pick_tag_ids(fandoms, freeforms))
            total_words = 0
            for position in range(1, chapter_count + 1):
                content = self.paragraphs(4, 14)
                words = count_words(content)
                total_words += words
                published_at = None
                if work.published_at:
                    published_at = min(self.now, work.published_at + timedelta(days=7 * (position - 1)))
                chapters.append(
                    Chapter(
                        work=work,
                        position=position,
                        title=self.fake.sentence(nb_words=rng.randint(2, 5)).rstrip(".") if chapter_count > 1 else "",
                        content=content,
                        word_count=words,
                        status=work.status,
                        published_at=published_at,
                    )
                )
            work.word_count = total_words
            # Grava em lotes para não estourar a memória do container
            if len(chapters) >= BATCH:
                Chapter.objects.bulk_create(chapters)
                total_chapters += len(chapters)
                chapters = []
            if len(work_tags) >= BATCH * 5:
                WorkTag.objects.bulk_create(work_tags, batch_size=BATCH)
                work_tags = []
        Chapter.objects.bulk_create(chapters, batch_size=BATCH)
        total_chapters += len(chapters)
        WorkTag.objects.bulk_create(work_tags, batch_size=BATCH)
        Work.objects.bulk_update(works, ["word_count"], batch_size=BATCH)
        self.log(f"{len(works)} obras e {total_chapters} capítulos.")
        return works, main_pseud

    def create_series(self, works, main_pseud):
        works_by_pseud = defaultdict(list)
        for work in works:
            if work.status == PublicationStatus.PUBLISHED:
                works_by_pseud[main_pseud[work.pk]].append(work)
        entries = []
        series_count = 0
        for pseud, pseud_works in works_by_pseud.items():
            if len(pseud_works) < 2 or self.rng.random() > 0.15:
                continue
            series = Series.objects.create(
                title=self.fake.sentence(nb_words=self.rng.randint(2, 4)).rstrip("."),
                summary=f"<p>{self.fake.paragraph()}</p>",
                is_complete=self.rng.random() < 0.4,
            )
            series.pseuds.add(pseud)
            chosen = self.rng.sample(pseud_works, k=min(len(pseud_works), self.rng.randint(2, 4)))
            chosen.sort(key=lambda work: work.published_at)
            entries.extend(
                SeriesWork(series=series, work=work, position=position) for position, work in enumerate(chosen, 1)
            )
            series_count += 1
        SeriesWork.objects.bulk_create(entries, batch_size=BATCH)
        self.log(f"{series_count} séries.")

    # --- Kudos, bookmarks e comentários ---

    def create_interactions(self, works, users, pseuds, freeforms):
        rng = self.rng
        published = [work for work in works if work.status == PublicationStatus.PUBLISHED]

        kudos = []
        for work in published:
            amount = min(len(users), int(rng.expovariate(1 / 8)))
            kudos.extend(Kudos(work=work, user=user) for user in rng.sample(users, k=amount))
            kudos.extend(
                Kudos(work=work, guest_key=f"{rng.getrandbits(256):064x}") for _ in range(int(rng.expovariate(1 / 2)))
            )
        Kudos.objects.bulk_create(kudos, batch_size=BATCH)

        bookmarks = []
        for work in published:
            amount = min(len(pseuds), int(rng.expovariate(1 / 2)))
            bookmarks.extend(
                Bookmark(
                    pseud=pseud,
                    work=work,
                    notes=self.fake.sentence() if rng.random() < 0.3 else "",
                    is_private=rng.random() < 0.1,
                    is_rec=rng.random() < 0.15,
                )
                for pseud in rng.sample(pseuds, k=amount)
            )
        bookmarks = Bookmark.objects.bulk_create(bookmarks, batch_size=BATCH)
        BookmarkTag = Bookmark.tags.through
        bookmark_tags = []
        for bookmark in bookmarks:
            if freeforms and rng.random() < 0.3:
                bookmark_tags.extend(
                    BookmarkTag(bookmark_id=bookmark.pk, tag_id=tag.pk)
                    for tag in rng.sample(freeforms, k=min(len(freeforms), rng.randint(1, 3)))
                )
        BookmarkTag.objects.bulk_create(bookmark_tags, batch_size=BATCH)

        chapter_ids = list(
            Chapter.objects.filter(work__in=published, status=PublicationStatus.PUBLISHED).values_list("pk", flat=True)
        )
        comments = []
        for chapter_id in chapter_ids:
            if rng.random() < 0.3:
                comments.extend(
                    Comment(chapter_id=chapter_id, pseud=rng.choice(pseuds), content=self.fake.paragraph())
                    for _ in range(rng.randint(1, 5))
                )
        comments = Comment.objects.bulk_create(comments, batch_size=BATCH)
        replies = [
            Comment(chapter_id=comment.chapter_id, parent=comment, pseud=rng.choice(pseuds), content=self.fake.sentence())
            for comment in comments
            if rng.random() < 0.25
        ]
        Comment.objects.bulk_create(replies, batch_size=BATCH)
        self.log(
            f"{len(kudos)} kudos, {len(bookmarks)} bookmarks, {len(comments) + len(replies)} comentários."
        )

    def update_tag_counts(self):
        WorkTag = Work.tags.through
        uses = WorkTag.objects.filter(tag_id=OuterRef("pk")).values("tag_id").annotate(total=Count("*")).values("total")
        Tag.objects.update(use_count=Coalesce(Subquery(uses), 0))
