from allauth.account import app_settings
from allauth.account.stages import EmailVerificationStage as BaseEmailVerificationStage


class EmailVerificationStage(BaseEmailVerificationStage):
    """Com a aprovação automática ligada, confirmar o e-mail vira opcional (o site ainda não envia e-mails)."""

    def handle(self):
        from core.models import SiteSettings

        mandatory = app_settings.EmailVerificationMethod.MANDATORY
        if self.login.email_verification == mandatory and SiteSettings.current().auto_approve_signups:
            self.login.email_verification = app_settings.EmailVerificationMethod.OPTIONAL
        return super().handle()
