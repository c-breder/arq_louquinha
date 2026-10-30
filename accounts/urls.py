from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("aguardando-aprovacao/", views.pending_approval, name="pending_approval"),
    path("preferencias/", views.preferences, name="preferences"),
    path("pseudonimos/", views.pseud_list, name="pseuds"),
    path("pseudonimos/novo/", views.pseud_form, name="pseud_create"),
    path("pseudonimos/<int:pseud_id>/editar/", views.pseud_form, name="pseud_edit"),
    path("pseudonimos/<int:pseud_id>/excluir/", views.pseud_delete, name="pseud_delete"),
    path("pseudonimos/<int:pseud_id>/padrao/", views.pseud_make_default, name="pseud_make_default"),
    path("exportar-dados/", views.export_data, name="export_data"),
    path("excluir/", views.delete_account, name="delete_account"),
]
