from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django import forms
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from .listing import base_listings
from .models import Series, SeriesWork
from .sanitize import autoparagraph, clean_html
from .services import user_can_edit


class SeriesForm(forms.ModelForm):
    class Meta:
        model = Series
        fields = ["title", "summary", "notes", "is_complete"]
        widgets = {"summary": forms.Textarea(attrs={"rows": 3}), "notes": forms.Textarea(attrs={"rows": 3})}

    def clean_summary(self):
        return clean_html(autoparagraph(self.cleaned_data["summary"]))

    def clean_notes(self):
        return clean_html(autoparagraph(self.cleaned_data["notes"]))


class AddToSeriesForm(forms.Form):
    series = forms.ModelChoiceField(label=gettext_lazy("Série existente"), queryset=Series.objects.none(), required=False)
    new_title = forms.CharField(label=gettext_lazy("ou crie uma nova"), max_length=255, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["series"].queryset = Series.objects.filter(pseuds__user=user).distinct()

    def clean(self):
        data = super().clean()
        if not data.get("series") and not data.get("new_title", "").strip():
            raise forms.ValidationError(_("Escolha uma série ou dê um nome para a nova."))
        return data


def user_can_edit_series(user, series):
    return user.is_authenticated and series.pseuds.filter(user=user).exists()


def series_nav(work, user):
    """Para a página da obra: 'Parte N da série X' com anterior e próxima (só obras visíveis)."""
    result = []
    for entry in work.series_entries.select_related("series"):
        ordered = list(entry.series.entries.order_by("position").values_list("work_id", flat=True))
        visible = set(base_listings(user).filter(work_id__in=ordered).values_list("work_id", flat=True)) | {work.pk}
        ids = [work_id for work_id in ordered if work_id in visible]
        index = ids.index(work.pk)
        result.append(
            {
                "series": entry.series,
                "part": index + 1,
                "previous": ids[index - 1] if index > 0 else None,
                "next": ids[index + 1] if index + 1 < len(ids) else None,
            }
        )
    return result


def series_detail(request, series_id):
    series = get_object_or_404(Series, pk=series_id)
    entries = list(series.entries.order_by("position"))
    listings = {listing.work_id: listing for listing in base_listings(request.user).filter(work_id__in=[e.work_id for e in entries])}
    visible = [(entry, listings[entry.work_id]) for entry in entries if entry.work_id in listings]
    if not visible and not user_can_edit_series(request.user, series):
        raise Http404
    return render(
        request,
        "works/series_detail.html",
        {
            "series": series,
            "items": visible,
            "authors": series.pseuds.select_related("user"),
            "total_words": sum(listing.word_count for _entry, listing in visible),
            "can_edit": user_can_edit_series(request.user, series),
        },
    )


@login_required
def series_edit(request, series_id):
    series = get_object_or_404(Series, pk=series_id)
    if not user_can_edit_series(request.user, series):
        raise PermissionDenied
    form = SeriesForm(request.POST or None, instance=series)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Série salva."))
        return redirect("works:series", series_id=series.pk)
    entries = series.entries.select_related("work").order_by("position")
    return render(request, "works/series_form.html", {"form": form, "series": series, "entries": entries})


@login_required
@require_POST
@transaction.atomic
def series_move(request, series_id, entry_id, direction):
    series = get_object_or_404(Series, pk=series_id)
    if not user_can_edit_series(request.user, series):
        raise PermissionDenied
    entries = list(series.entries.order_by("position"))
    index = next(i for i, entry in enumerate(entries) if entry.pk == entry_id)
    other = index - 1 if direction == "subir" else index + 1
    if 0 <= other < len(entries):
        entries[index], entries[other] = entries[other], entries[index]
        for position, entry in enumerate(entries, 1):
            SeriesWork.objects.filter(pk=entry.pk).update(position=position)
    return redirect("works:series_edit", series_id=series.pk)


@login_required
@require_POST
@transaction.atomic
def add_to_series(request, work_id):
    from .models import Work

    work = get_object_or_404(Work, pk=work_id)
    if not user_can_edit(request.user, work):
        raise PermissionDenied
    form = AddToSeriesForm(request.POST, user=request.user)
    if not form.is_valid():
        for error in form.non_field_errors():
            messages.error(request, error)
        return redirect("works:edit", work_id=work.pk)
    series = form.cleaned_data.get("series")
    if series is None:
        series = Series.objects.create(title=form.cleaned_data["new_title"].strip())
        series.pseuds.add(request.user.default_pseud)
    if not series.entries.filter(work=work).exists():
        last = series.entries.aggregate(last=Max("position"))["last"] or 0
        SeriesWork.objects.create(series=series, work=work, position=last + 1)
    messages.success(request, _("Obra adicionada à série “%(title)s”.") % {"title": series.title})
    return redirect("works:edit", work_id=work.pk)


@login_required
@require_POST
@transaction.atomic
def remove_from_series(request, work_id, series_id):
    entry = get_object_or_404(SeriesWork, work_id=work_id, series_id=series_id)
    if not user_can_edit(request.user, entry.work):
        raise PermissionDenied
    series = entry.series
    entry.delete()
    for position, item in enumerate(series.entries.order_by("position"), 1):
        SeriesWork.objects.filter(pk=item.pk).update(position=position)
    if not series.entries.exists():
        series.delete()  # série vazia some
    messages.success(request, _("Obra removida da série."))
    return redirect("works:edit", work_id=work_id)

