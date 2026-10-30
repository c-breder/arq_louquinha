from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Conversation(models.Model):
    # Conversa 1 a 1; user_a é sempre o de menor id, para cada par existir uma vez só
    user_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    user_b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(null=True)
    last_sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    a_read_at = models.DateTimeField(null=True)
    b_read_at = models.DateTimeField(null=True)

    class Meta:
        verbose_name = _("conversa")
        verbose_name_plural = _("conversas")
        constraints = [
            models.UniqueConstraint(fields=["user_a", "user_b"], name="conversation_pair_unique"),
            models.CheckConstraint(condition=Q(user_a__lt=F("user_b")), name="conversation_pair_ordered"),
        ]

    def __str__(self):
        return f"{self.user_a} ↔ {self.user_b}"

    @classmethod
    def between(cls, first, second):
        low, high = sorted([first, second], key=lambda user: user.pk)
        conversation, _created = cls.objects.get_or_create(user_a=low, user_b=high)
        return conversation

    @classmethod
    def of(cls, user):
        return cls.objects.filter(Q(user_a=user) | Q(user_b=user))

    @classmethod
    def unread_for(cls, user):
        return cls.of(user).filter(last_message_at__isnull=False).exclude(last_sender=user).filter(
            (Q(user_a=user) & (Q(a_read_at__isnull=True) | Q(a_read_at__lt=F("last_message_at"))))
            | (Q(user_b=user) & (Q(b_read_at__isnull=True) | Q(b_read_at__lt=F("last_message_at"))))
        )

    def includes(self, user):
        return user.pk in (self.user_a_id, self.user_b_id)

    def other(self, user):
        return self.user_b if user.pk == self.user_a_id else self.user_a

    def mark_read(self, user):
        field = "a_read_at" if user.pk == self.user_a_id else "b_read_at"
        setattr(self, field, timezone.now())
        self.save(update_fields=[field])


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    body = models.TextField(_("mensagem"))
    created_at = models.DateTimeField(auto_now_add=True)
    hidden_by_moderator = models.BooleanField(_("oculta pela moderação"), default=False)

    class Meta:
        verbose_name = _("mensagem")
        verbose_name_plural = _("mensagens")
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return self.body[:60]
