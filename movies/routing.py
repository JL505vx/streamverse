from django.urls import re_path

from .consumers import WatchPartyConsumer


websocket_urlpatterns = [
    re_path(r'^ws/watch-party/(?P<slug>[-a-zA-Z0-9_]+)/(?P<code>[A-Z0-9]+)/$', WatchPartyConsumer.as_asgi()),
]
