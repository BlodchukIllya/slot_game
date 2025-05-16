from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler404
from game import views as game_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('game.urls')),  # All game-related URLs
]

# Custom error handlers
handler404 = 'game.views.page_not_found'

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
