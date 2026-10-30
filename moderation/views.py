from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from interactions.models import Comment
from messaging.models import Message
from works.models import PublicationStatus, Work

from .models import Report


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "details"]
        widgets = {"reason": forms.RadioSelect, "details": forms.Textarea(attrs={"rows": 4})}


def find_target(request, kind, object_id):
    # Só dá para denunciar o que a pessoa consegue ver
    user = request.user
    if kind == "work":
        target = Work.objects.filter(pk=object_id, status=PublicationStatus.PUBLISHED).first()
        return target, (target and reverse_work(target))
    if kind == "comment":
        target = Comment.objects.select_related("chapter").filter(pk=object_id).first()
        if target:
            return target, f"/obras/{target.chapter.work_id}/capitulos/{target.chapter.position}/#comentario-{target.pk}"
    if kind == "user":
        target = get_user_model().objects.filter(pk=object_id, is_active=True).first()
        return target, (target and f"/usuarios/{target.username}/")
    if kind == "message":
        target = Message.objects.select_related("conversation").filter(pk=object_id).first()
        if target and target.conversation.includes(user) and target.sender_id != user.pk:
            return target, f"/mensagens/{target.conversation_id}/"
    return None, None


def reverse_work(work):
    return f"/obras/{work.pk}/"


@login_required
def report(request, kind, object_id):
    target, back = find_target(request, kind, object_id)
    if target is None:
        raise Http404
    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        content_type = ContentType.objects.get_for_model(target)
        already = Report.objects.filter(
            reporter=request.user, content_type=content_type, object_id=target.pk, status=Report.Status.OPEN
        ).exists()
        if not already:
            item = form.save(commit=False)
            item.reporter = request.user
            item.content_type = content_type
            item.object_id = target.pk
            item.save()
        messages.success(request, _("Denúncia enviada. Obrigado por avisar; a moderação vai analisar."))
        return redirect(back)
    return render(request, "moderation/report.html", {"form": form, "target": target, "back": back})
