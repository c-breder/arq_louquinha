from django.conf import settings
from django.db import migrations

# Texto do "Sobre" tirado da descrição escrita pela dona do site; os outros dois ela escreve pelo admin
PAGES = [
    (
        "/sobre/",
        "Sobre",
        "<p>O Arquivo Louquinha é uma plataforma independente de publicação, organização e leitura de fanfics, "
        "criada inicialmente a partir do fandom Louquinha, da novela Três Graças, e aberta a outros fandoms e "
        "comunidades.</p><p>É uma biblioteca digital de histórias, feita para preservar o que a gente escreve e lê.</p>",
    ),
    ("/termos/", "Termos de Uso", "<p>Em construção.</p>"),
    ("/contato/", "Contato", "<p>Em construção.</p>"),
]


def create_pages(apps, schema_editor):
    FlatPage = apps.get_model("flatpages", "FlatPage")
    Site = apps.get_model("sites", "Site")
    # Num banco novo o site padrão só seria criado depois das migrations; criamos aqui
    site, _created = Site.objects.get_or_create(
        pk=settings.SITE_ID, defaults={"domain": "example.com", "name": "example.com"}
    )
    for url, title, content in PAGES:
        page, _created = FlatPage.objects.get_or_create(url=url, defaults={"title": title, "content": content})
        page.sites.add(site)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_postgres_extensions"),
        ("flatpages", "0001_initial"),
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [migrations.RunPython(create_pages, migrations.RunPython.noop)]
