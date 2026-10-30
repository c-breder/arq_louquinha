import json

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.languages import set_language_cookie

from . import services
from .forms import DeleteAccountForm, PreferencesForm, PseudForm


def pending_approval(request):
    if request.user.is_authenticated and request.user.is_approved:
        return redirect("home")
    return render(request, "accounts/pending_approval.html")


@login_required
def preferences(request):
    form = PreferencesForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        # Mensagem já no idioma novo
        with translation.override(user.language):
            messages.success(request, _("Preferências salvas."))
        response = redirect("accounts:preferences")
        set_language_cookie(response, user.language)
        return response
    return render(request, "accounts/preferences.html", {"form": form})


# --- Pseudônimos ---


@login_required
def pseud_list(request):
    return render(request, "accounts/pseud_list.html", {"pseuds": request.user.pseuds.all()})


@login_required
def pseud_form(request, pseud_id=None):
    pseud = get_object_or_404(request.user.pseuds, pk=pseud_id) if pseud_id else None
    form = PseudForm(request.POST or None, request.FILES or None, instance=pseud, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Pseudônimo salvo."))
        return redirect("accounts:pseuds")
    return render(request, "accounts/pseud_form.html", {"form": form, "pseud": pseud})


@login_required
def pseud_delete(request, pseud_id):
    pseud = get_object_or_404(request.user.pseuds, pk=pseud_id)
    if pseud.is_default:
        messages.error(request, _("O pseudônimo padrão não pode ser excluído."))
        return redirect("accounts:pseuds")
    if request.method == "POST":
        services.delete_pseud(pseud)
        messages.success(request, _("Pseudônimo excluído. As obras dele passaram para o seu pseudônimo padrão."))
        return redirect("accounts:pseuds")
    return render(request, "accounts/pseud_confirm_delete.html", {"pseud": pseud})


@login_required
@require_POST
def pseud_make_default(request, pseud_id):
    services.set_default_pseud(get_object_or_404(request.user.pseuds, pk=pseud_id))
    messages.success(request, _("Pseudônimo padrão alterado."))
    return redirect("accounts:pseuds")


# --- LGPD: exportar e excluir ---


@login_required
def export_data(request):
    data = services.export_user_data(request.user)
    response = HttpResponse(
        json.dumps(data, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="meus-dados-{request.user.username}.json"'
    return response


@login_required
def delete_account(request):
    form = DeleteAccountForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        user = request.user
        logout(request)
        services.delete_account(user, form.cleaned_data["works"])
        messages.success(request, _("Sua conta foi excluída."))
        return redirect("home")
    return render(request, "accounts/delete_account.html", {"form": form})
