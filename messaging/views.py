from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from interactions.services import can_interact

from .models import Conversation, Message

MAX_MESSAGE = 5000


class MessageForm(forms.Form):
    body = forms.CharField(label=gettext_lazy("Mensagem"), widget=forms.Textarea(attrs={"rows": 4}), max_length=MAX_MESSAGE)


class NewMessageForm(MessageForm):
    to = forms.CharField(label=gettext_lazy("Para (nome de usuário)"), max_length=150)

    field_order = ["to", "body"]

    def __init__(self, *args, sender, **kwargs):
        super().__init__(*args, **kwargs)
        self.sender = sender

    def clean_to(self):
        recipient = get_user_model().objects.filter(
            username__iexact=self.cleaned_data["to"].strip(), is_active=True, is_approved=True
        ).first()
        if recipient is None:
            raise ValidationError(_("Não encontramos uma conta ativa com esse nome."))
        if recipient == self.sender:
            raise ValidationError(_("Você não pode mandar mensagem para si mesmo(a)."))
        if not recipient.allow_messages:
            raise ValidationError(_("Essa pessoa não aceita mensagens privadas."))
        return recipient


def rate_exceeded(user):
    key = f"messages:{user.pk}:{int(timezone.now().timestamp() // 3600)}"
    cache.add(key, 0, timeout=3700)
    return cache.incr(key) > settings.MESSAGES_PER_HOUR


@transaction.atomic
def send(conversation, sender, body):
    message = Message.objects.create(conversation=conversation, sender=sender, body=body.strip())
    conversation.last_message_at = message.created_at
    conversation.last_sender = sender
    conversation.save(update_fields=["last_message_at", "last_sender"])
    conversation.mark_read(sender)
    return message


def require_messaging(user):
    if not can_interact(user):
        raise PermissionDenied


@login_required
def inbox(request):
    require_messaging(request.user)
    conversations = list(
        Conversation.of(request.user)
        .filter(last_message_at__isnull=False)
        .select_related("user_a", "user_b", "last_sender")
        .order_by("-last_message_at")
    )
    unread = set(Conversation.unread_for(request.user).values_list("pk", flat=True))
    rows = [(conversation, conversation.other(request.user), conversation.pk in unread) for conversation in conversations]
    return render(request, "messaging/inbox.html", {"rows": rows})


@login_required
def new_message(request):
    require_messaging(request.user)
    form = NewMessageForm(request.POST or None, sender=request.user, initial={"to": request.GET.get("para", "")})
    if request.method == "POST" and form.is_valid():
        if rate_exceeded(request.user):
            messages.error(request, _("Você mandou mensagens demais na última hora. Tente mais tarde."))
        else:
            conversation = Conversation.between(request.user, form.cleaned_data["to"])
            send(conversation, request.user, form.cleaned_data["body"])
            return redirect("messaging:thread", conversation_id=conversation.pk)
    return render(request, "messaging/new.html", {"form": form})


@login_required
def thread(request, conversation_id):
    require_messaging(request.user)
    conversation = get_object_or_404(Conversation.objects.select_related("user_a", "user_b"), pk=conversation_id)
    if not conversation.includes(request.user):
        raise PermissionDenied
    other = conversation.other(request.user)
    form = MessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not (other.is_active and other.allow_messages):
            messages.error(request, _("Essa pessoa não aceita mais mensagens privadas."))
        elif rate_exceeded(request.user):
            messages.error(request, _("Você mandou mensagens demais na última hora. Tente mais tarde."))
        else:
            send(conversation, request.user, form.cleaned_data["body"])
            return redirect("messaging:thread", conversation_id=conversation.pk)
    conversation.mark_read(request.user)
    history = conversation.messages.select_related("sender")
    return render(request, "messaging/thread.html", {"conversation": conversation, "other": other, "history": history, "form": form})
