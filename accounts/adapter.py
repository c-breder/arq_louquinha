from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return settings.SIGNUP_OPEN

    def get_login_stages(self):
        # Nossa etapa de e-mail respeita a aprovação automática das Configurações do site
        return [
            "accounts.stages.EmailVerificationStage" if stage == "allauth.account.stages.EmailVerificationStage" else stage
            for stage in super().get_login_stages()
        ]
