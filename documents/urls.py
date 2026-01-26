from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('upload/', views.upload_view, name='upload'),
    path('<int:document_id>/', views.document_view, name='view'),
    path('<int:document_id>/sections/', views.sections_view, name='sections'),
    path('<int:document_id>/download/', views.download_view, name='download'),
    path('<int:document_id>/delete/', views.delete_view, name='delete'),
    # Search endpoints moved here
    path('<int:document_id>/search/keyword/', views.keyword_search, name='keyword_search'),
    path('<int:document_id>/search/semantic/', views.semantic_search, name='semantic_search'),
]