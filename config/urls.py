from django.contrib import admin
from django.urls import include, path

from core.views import media_stream_view


urlpatterns = [
    path('admin/', admin.site.urls),
    path('media/<path:path>', media_stream_view, name='media_stream'),
    path('', include('movies.urls')),
    path('cuenta/', include('core.urls')),
]
