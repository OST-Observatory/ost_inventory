from django.urls import path

from .acl_views import (
    AccessControlView,
    GroupListView,
    access_save,
    group_add,
    group_add_member,
    group_delete,
    group_detail,
    group_remove_member,
)

app_name = "accounts"

urlpatterns = [
    path("access/", AccessControlView.as_view(), name="access"),
    path("access/save/", access_save, name="access_save"),
    path("groups/", GroupListView.as_view(), name="groups"),
    path("groups/add/", group_add, name="group_add"),
    path("groups/<int:pk>/", group_detail, name="group_detail"),
    path("groups/<int:pk>/add-member/", group_add_member, name="group_add_member"),
    path(
        "groups/<int:pk>/remove-member/<int:user_id>/",
        group_remove_member,
        name="group_remove_member",
    ),
    path("groups/<int:pk>/delete/", group_delete, name="group_delete"),
]
