from django.urls import path

from . import views

app_name = "sheets-api"

urlpatterns = [
    path("sheets/", views.spreadsheet_list, name="spreadsheet-list"),
    path("sheets/upload/", views.spreadsheet_upload, name="spreadsheet-upload"),
    path("sheets/<int:pk>/", views.spreadsheet_detail, name="spreadsheet-detail"),
    path("sheets/<int:pk>/export/", views.spreadsheet_export, name="spreadsheet-export"),
    path("sheets/<int:pk>/revisions/", views.revision_list, name="revision-list"),
    path("sheets/<int:pk>/revisions/<int:revision>/", views.revision_detail, name="revision-detail"),
    path("sheets/<int:pk>/revisions/<int:revision>/restore/", views.revision_restore, name="revision-restore"),
]
