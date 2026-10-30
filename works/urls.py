from django.urls import path

from . import import_views, series, views

app_name = "works"

urlpatterns = [
    path("obras/", views.search_works, name="search"),
    path("obras/nova/", views.work_create, name="create"),
    path("obras/importar/", import_views.import_work, name="import"),
    path("obras/<int:work_id>/importada/", import_views.import_result, name="import_result"),
    path("obras/imagens/enviar/", views.image_upload, name="image_upload"),
    path("obras/<int:work_id>/", views.work_detail, name="detail"),
    path("obras/<int:work_id>/completa/", views.work_full, name="full"),
    path("obras/<int:work_id>/editar/", views.work_edit, name="edit"),
    path("obras/<int:work_id>/excluir/", views.work_delete, name="delete"),
    path("obras/<int:work_id>/coautoria/convidar/", views.coauthor_invite, name="coauthor_invite"),
    path("obras/<int:work_id>/coautoria/sair/", views.leave_work, name="leave"),
    path("obras/<int:work_id>/capitulos/novo/", views.chapter_create, name="chapter_create"),
    path("obras/<int:work_id>/capitulos/<int:position>/", views.chapter_detail, name="chapter"),
    path("obras/<int:work_id>/capitulos/<int:position>/editar/", views.chapter_edit, name="chapter_edit"),
    path("obras/<int:work_id>/capitulos/<int:position>/excluir/", views.chapter_delete, name="chapter_delete"),
    path("obras/<int:work_id>/serie/", series.add_to_series, name="add_to_series"),
    path("obras/<int:work_id>/serie/<int:series_id>/remover/", series.remove_from_series, name="remove_from_series"),
    path("series/<int:series_id>/", series.series_detail, name="series"),
    path("series/<int:series_id>/editar/", series.series_edit, name="series_edit"),
    path("series/<int:series_id>/mover/<int:entry_id>/<str:direction>/", series.series_move, name="series_move"),
    path("minhas-obras/", views.my_works, name="my_works"),
    path("convites/", views.invitations, name="invitations"),
    path("convites/<int:authorship_id>/responder/", views.respond_invitation, name="respond_invitation"),
    path("usuarios/<str:username>/", views.user_profile, name="user_profile"),
]
