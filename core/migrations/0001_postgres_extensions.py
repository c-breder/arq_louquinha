from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    # unaccent e pg_trgm: usados pela busca (fase 4)
    operations = [
        UnaccentExtension(),
        TrigramExtension(),
    ]
