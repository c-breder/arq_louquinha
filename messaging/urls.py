from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("mensagens/", views.inbox, name="inbox"),
    path("mensagens/nova/", views.new_message, name="new"),
    path("mensagens/<int:conversation_id>/", views.thread, name="thread"),
]
