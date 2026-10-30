from django.urls import path

from . import views

app_name = "moderation"

urlpatterns = [
    path("denunciar/<str:kind>/<int:object_id>/", views.report, name="report"),
]
