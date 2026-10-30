from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tags.models import Tag
from tags.services import refresh_use_counts
from works.listing import refresh
from works.models import Chapter, PublicationStatus, Work, WorkAuthor
from works.text import count_words


class Command(BaseCommand):
    help = "Cria obras simples \"Teste 1\", \"Teste 2\"... publicadas na conta indicada (não duplica)."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="nome de usuário da dona das obras")
        parser.add_argument("--count", type=int, default=6, help="quantas obras (padrão 6)")

    @transaction.atomic
    def handle(self, *args, **options):
        owner = get_user_model().objects.filter(username=options["user"]).first()
        if owner is None:
            raise CommandError(f"Conta \"{options['user']}\" não encontrada.")
        fandom, _ = Tag.objects.get_or_create(name="Teste", defaults={"type": Tag.Type.FANDOM, "canonical": True})
        freeform, _ = Tag.objects.get_or_create(
            name="Obra de teste", defaults={"type": Tag.Type.FREEFORM, "canonical": True}
        )
        now = timezone.now()
        created = []
        for number in range(1, options["count"] + 1):
            title = f"Teste {number}"
            if Work.objects.filter(title=title, authorships__pseud__user=owner).exists():
                continue
            content = f"<p>Este é o texto da obra de teste {number}. Pode ser apagada a qualquer momento.</p>"
            work = Work.objects.create(
                title=title,
                summary=f"<p>Obra de teste {number}.</p>",
                rating=Work.Rating.GENERAL,
                warnings=[Work.Warning.NONE_APPLY],
                language="pt-br",
                is_complete=number % 2 == 0,  # metade concluída, metade em andamento
                expected_chapters=1 if number % 2 == 0 else None,
                status=PublicationStatus.PUBLISHED,
                published_at=now,
                word_count=count_words(content),
            )
            WorkAuthor.objects.create(work=work, pseud=owner.default_pseud, status=WorkAuthor.Status.ACCEPTED)
            Chapter.objects.create(
                work=work, position=1, content=content, word_count=count_words(content),
                status=PublicationStatus.PUBLISHED, published_at=now,
            )
            work.tags.set([fandom, freeform])
            created.append(work.pk)
        refresh_use_counts({fandom.pk, freeform.pk})
        refresh(created)
        self.stdout.write(self.style.SUCCESS(f"{len(created)} obra(s) de teste criada(s) para {owner.username}."))
