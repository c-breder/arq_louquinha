from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Marca o e-mail de uma conta como confirmado (útil enquanto o site não envia e-mails)."

    def add_arguments(self, parser):
        parser.add_argument("username", help="nome de usuário da conta")
        parser.add_argument("--approve", action="store_true", help="também aprova a conta")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"Conta \"{options['username']}\" não encontrada.")
        EmailAddress.objects.update_or_create(
            user=user, email=user.email, defaults={"verified": True, "primary": True}
        )
        if options["approve"] and not user.is_approved:
            from accounts.services import approve_user

            approve_user(user, by=None)
        self.stdout.write(self.style.SUCCESS(
            f"E-mail de {user.username} confirmado{' e conta aprovada' if options['approve'] else ''}."
        ))
