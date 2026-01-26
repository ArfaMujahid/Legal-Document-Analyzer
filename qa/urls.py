from django.urls import path
from . import views

app_name = 'qa'

urlpatterns = [
    path('ask/', views.ask_question, name='ask'),
    path('history/', views.qa_history, name='history'),
    path('history/<int:history_id>/', views.delete_qa_history, name='delete_history'),
]