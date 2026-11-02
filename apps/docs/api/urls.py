from django.urls import path

from . import views

app_name = "docs-api"

urlpatterns = [
    path("docs/spreadsheets/", views.spreadsheet_list, name="spreadsheet-list"),
    path("docs/spreadsheets/upload/", views.spreadsheet_upload, name="spreadsheet-upload"),
    path("docs/spreadsheets/<int:pk>/", views.spreadsheet_detail, name="spreadsheet-detail"),
    path("docs/spreadsheets/<int:pk>/export/", views.spreadsheet_export, name="spreadsheet-export"),
    path("docs/spreadsheets/<int:pk>/revisions/", views.revision_list, name="revision-list"),
    path("docs/spreadsheets/<int:pk>/revisions/<int:revision>/", views.revision_detail, name="revision-detail"),
    path("docs/spreadsheets/<int:pk>/revisions/<int:revision>/restore/", views.revision_restore, name="revision-restore"),
]
