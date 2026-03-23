from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import media_stream_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('movies.urls')),
    path('cuenta/', include('core.urls')),
    path('media/<path:path>', media_stream_view, name='media_stream'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
