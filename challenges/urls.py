from django.urls import path

from . import views

app_name = "challenges"

urlpatterns = [
    path("colecoes/", views.collection_index, name="index"),
    path("colecoes/nova/", views.collection_form, name="create"),
    path("colecoes/<slug:slug>/", views.collection_detail, name="detail"),
    path("colecoes/<slug:slug>/editar/", views.collection_form, name="edit"),
    path("colecoes/<slug:slug>/gerenciar/", views.collection_manage, name="manage"),
    path("colecoes/<slug:slug>/prompts/", views.add_prompt, name="add_prompt"),
    path("obras/<int:work_id>/colecoes/", views.add_work, name="add_work"),
    path("obras/<int:work_id>/colecoes/<slug:slug>/remover/", views.remove_work, name="remove_work"),
]
