from django.urls import path

from . import views

app_name = "tags"

urlpatterns = [
    path("tags/", views.tag_search, name="search"),
    path("tags/autocompletar/", views.autocomplete, name="autocomplete"),
    path("tags/<int:tag_id>/", views.tag_detail, name="detail"),
    path("fandoms/", views.fandom_index, name="fandoms"),
    path("wrangling/", views.wrangling_home, name="wrangling"),
    path("wrangling/em-lote/", views.wrangling_bulk, name="bulk"),
    path("wrangling/tags/<int:tag_id>/", views.wrangle_tag, name="wrangle"),
]
