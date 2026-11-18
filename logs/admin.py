from django.contrib import admin

from .models import ErrorLog


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'stage', 'user', 'document', 'message')
    list_filter = ('stage',)
