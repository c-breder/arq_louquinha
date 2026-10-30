from django.db import migrations, models


# Antes: 0 Básico, 1 Capa, 2 Completo. Agora: 0 Básico, 1 Imagens.
def forwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(media_level=1).update(media_level=0)
    User.objects.filter(media_level=2).update(media_level=1)


def backwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(media_level=1).update(media_level=2)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="user",
            name="media_level",
            field=models.PositiveSmallIntegerField(
                choices=[(0, "Básico (só avatar)"), (1, "Imagens (avatar e imagens no texto)")],
                default=0,
                verbose_name="nível de mídia",
            ),
        ),
    ]
