from django.core.management.base import BaseCommand

from core.status import collect


class Command(BaseCommand):
    help = "Mostra tamanho do banco, contagens, Redis, mídia e espaço em disco."

    def handle(self, *args, **options):
        data = collect()
        out = self.stdout.write
        out("== Banco")
        out(f"  Tamanho: {data['database_mb']} MB")
        for table in data["largest_tables"]:
            out(f"    {table['table']}: {table['mb']} MB")
        counts = data["counts"]
        out(
            f"  Usuários {counts['users']} · obras {counts['works']} · capítulos {counts['chapters']}"
            f" · tags {counts['tags']} · denúncias abertas {counts['open_reports']}"
        )
        out("== Redis")
        out(f"  Memória: {data['redis_memory']} · na fila: {data['pending']['hits']} acessos, {data['pending']['kudos']} kudos")
        out("== Disco")
        disk = data["disk"]
        out(f"  Mídia: {data['media_mb']} MB · disco: {disk['free_gb']} GB livres de {disk['total_gb']} GB ({disk['used_percent']}% usado)")
