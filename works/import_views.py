from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.models import SiteSettings
from interactions.services import can_interact

from .importer import ImportProblem, parse_pdf
from .services import create_imported_work
from .views import get_editable_work


class ImportForm(forms.Form):
    file = forms.FileField(
        label=gettext_lazy("PDF baixado do AO3"),
        widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf"}),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > settings.MAX_IMPORT_MB * 1024 * 1024:
            raise ValidationError(_("O arquivo passa de %(max)d MB.") % {"max": settings.MAX_IMPORT_MB})
        if upload.read(5) != b"%PDF-":
            raise ValidationError(_("Esse arquivo não é um PDF."))
        upload.seek(0)
        return upload


def import_limit_reached(user):
    key = f"imports:{user.pk}:{int(timezone.now().timestamp() // 3600)}"
    cache.add(key, 0, timeout=3700)
    return cache.incr(key) > settings.IMPORTS_PER_HOUR


@login_required
def import_work(request):
    if not can_interact(request.user):
        raise PermissionDenied
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        if import_limit_reached(request.user):
            messages.error(request, _("Muitas importações na última hora. Tente mais tarde."))
        else:
            try:
                imported = parse_pdf(form.cleaned_data["file"])
            except ImportProblem as problem:
                form.add_error("file", str(problem))
            else:
                work, problems = create_imported_work(request.user, imported)
                for problem in problems:
                    messages.warning(request, problem)
                return redirect("works:import_result", work_id=work.pk)
    direct_url = SiteSettings.current().direct_url.rstrip("/")
    return render(
        request,
        "works/import_form.html",
        {"form": form, "max_mb": settings.MAX_IMPORT_MB, "direct_url": direct_url},
    )


@login_required
def import_result(request, work_id):
    work = get_editable_work(request, work_id)
    return render(
        request,
        "works/import_result.html",
        {"work": work, "chapters": work.chapters.order_by("position"), "tags": work.tags.order_by("type", "name")},
    )
