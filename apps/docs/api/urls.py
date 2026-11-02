from django.urls import path

from . import documents, views

app_name = "docs-api"

urlpatterns = [
    path("docs/spreadsheets/", views.spreadsheet_list, name="spreadsheet-list"),
    path("docs/spreadsheets/upload/", views.spreadsheet_upload, name="spreadsheet-upload"),
    path("docs/spreadsheets/<int:pk>/", views.spreadsheet_detail, name="spreadsheet-detail"),
    path("docs/spreadsheets/<int:pk>/export/", views.spreadsheet_export, name="spreadsheet-export"),
    path("docs/spreadsheets/<int:pk>/revisions/", views.revision_list, name="revision-list"),
    path("docs/spreadsheets/<int:pk>/revisions/<int:revision>/", views.revision_detail, name="revision-detail"),
    path("docs/spreadsheets/<int:pk>/revisions/<int:revision>/restore/", views.revision_restore, name="revision-restore"),
    # 文档转换与 Dify 推送
    path("docs/documents/", documents.document_list, name="document-list"),
    path("docs/documents/<int:pk>/", documents.document_detail, name="document-detail"),
    path("docs/documents/<int:pk>/push/", documents.document_push, name="document-push"),
    path("docs/documents/<int:pk>/status/", documents.document_status, name="document-status"),
]
