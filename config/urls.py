from django.contrib import admin
from django.urls import include, path

from core.views import media_stream_view, offline_view, pwa_manifest_view, pwa_service_worker_view, video_processing_status_view


urlpatterns = [
    path('admin/', admin.site.urls),
    path('manifest.webmanifest', pwa_manifest_view, name='pwa_manifest'),
    path('sw.js', pwa_service_worker_view, name='pwa_service_worker'),
    path('offline/', offline_view, name='offline'),
    path('api/video/<int:pk>/status', video_processing_status_view, name='video_processing_status'),
    path('media/<path:path>', media_stream_view, name='media_stream'),
    path('', include('movies.urls')),
    path('cuenta/', include('core.urls')),
]
