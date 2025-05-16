from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Player
from decimal import Decimal

@receiver(post_save, sender=User)
def create_player_profile(sender, instance, created, **kwargs):
    """
    Signal to create a Player profile when a new User is created.
    """
    if created:
        try:
            # Check if player already exists to avoid UNIQUE constraint error
            if not hasattr(instance, 'player'):
                Player.objects.create(user=instance, balance=Decimal('1000.00'))
        except Exception as e:
            print(f"Error creating player profile: {e}")

@receiver(post_save, sender=User)
def save_player_profile(sender, instance, **kwargs):
    """
    Signal to save the Player profile when the User is saved.
    """
    try:
        # Only save if player exists
        if hasattr(instance, 'player'):
            instance.player.save()
    except Exception as e:
        print(f"Error saving player profile: {e}")
