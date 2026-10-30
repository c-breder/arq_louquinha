from django.urls import path

from . import views

app_name = "interactions"

urlpatterns = [
    path("obras/<int:work_id>/kudos/", views.give_kudos, name="kudos"),
    path("obras/<int:work_id>/capitulos/<int:position>/comentar/", views.add_comment, name="comment"),
    path("comentarios/<int:comment_id>/editar/", views.edit_comment, name="comment_edit"),
    path("comentarios/<int:comment_id>/apagar/", views.delete_comment, name="comment_delete"),
    path("obras/<int:work_id>/bookmark/", views.bookmark_work, name="bookmark"),
    path("obras/<int:work_id>/bookmarks/", views.work_bookmarks, name="work_bookmarks"),
    path("bookmarks/<int:bookmark_id>/apagar/", views.delete_bookmark, name="bookmark_delete"),
    path("usuarios/<str:username>/bookmarks/", views.user_bookmarks, name="user_bookmarks"),
]
