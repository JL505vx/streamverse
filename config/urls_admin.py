from django.contrib import admin
from django.urls import include, path

from core.views import media_stream_view, video_processing_status_view


urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/video/<int:pk>/status', video_processing_status_view, name='video_processing_status'),
    path('media/<path:path>', media_stream_view, name='media_stream'),
    path('', include('core.urls_admin')),
]
