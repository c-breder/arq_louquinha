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
        from accounts.services import apply_pre_approval, approve_user

        # Mesma regra do link de confirmação: e-mail pré-aprovado aprova a conta
        pre_approved = apply_pre_approval(user, user.email)
        if options["approve"] and not user.is_approved:
            approve_user(user, by=None)
        approved = pre_approved or options["approve"]
        self.stdout.write(self.style.SUCCESS(
            f"E-mail de {user.username} confirmado{' e conta aprovada' if approved else ''}"
            f"{' (estava pré-aprovado)' if pre_approved else ''}."
        ))
