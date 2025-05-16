from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),  # Root URL
    path('game/', views.slot_game, name='slot_game'),  # Main game page
    path('play/', views.play, name='play'),  # Handle game play (POST only)
    path('register/', views.register, name='register'),  # Registration page
    path('history/', views.game_history, name='game_history'),  # Game history page
    path('profile/', views.profile, name='profile'),  # User profile page
    
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]

