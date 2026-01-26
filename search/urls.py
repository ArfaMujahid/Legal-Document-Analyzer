from django.urls import path
from . import views

app_name = 'search'

urlpatterns = [
    path('', views.search_view, name='search'),
    path('keyword/', views.keyword_search, name='keyword_search'),
    path('semantic/', views.semantic_search, name='semantic_search'),
    path('history/', views.search_history, name='search_history'),
]