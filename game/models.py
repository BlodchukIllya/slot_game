from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum, F, Case, When, Value
from django.core.validators import MinValueValidator
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid

class Player(models.Model):
    """Player model extending the default User model"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='player')
    balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1000.00,
        validators=[MinValueValidator(0)]
    )
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Гравець'
        verbose_name_plural = 'Гравці'

    def __str__(self):
        return f"{self.user.username}'s Profile (Balance: {self.balance} ₴)"

    def update_balance(self, amount):
        """Update player's balance safely with transaction"""
        self.balance += Decimal(str(amount))
        self.save(update_fields=['balance', 'updated_at'])
        return self.balance
        
    @property
    def total_games_played(self):
        """Return total number of games played by this player"""
        return self.game_sessions.count()
        
    @property
    def total_won(self):
        """Return total amount won by this player"""
        return self.game_sessions.aggregate(
            total=Sum(
                Case(
                    When(result=GameSession.GameResult.WIN, then='win_amount'),
                    default=0,
                    output_field=DecimalField()
                )
            )
        )['total'] or 0
        
    def update_activity(self):
        """Update the last activity timestamp"""
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])
        
    def get_absolute_url(self):
        return reverse('admin:game_player_change', args=[self.id])


class GameSession(models.Model):
    """Tracks each game session for a player"""
    class GameResult(models.TextChoices):
        WIN = 'WIN', 'Перемога'
        LOSS = 'LOSS', 'Поразка'
        JACKPOT = 'JACKPOT', 'Джекпот'
        
    class Meta:
        verbose_name = 'Ігрова сесія'
        verbose_name_plural = 'Ігрові сесії'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['player', 'created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['result']),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='game_sessions')
    bet_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    result = models.CharField(max_length=10, choices=GameResult.choices)
    win_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    numbers = models.JSONField()  # Store the game result numbers
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['player', 'created_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.player.user.username}'s game at {self.created_at} - {self.result.upper()}"

    def save(self, *args, **kwargs):
        # Ensure win_amount is positive for wins, negative for losses
        if self.result == self.GameResult.LOSS:
            self.win_amount = -self.bet_amount
        super().save(*args, **kwargs)


class Transaction(models.Model):
    """Tracks all financial transactions"""
    class TransactionType(models.TextChoices):
        BET = 'BET', 'Ставка'
        WIN = 'WIN', 'Виграш'
        DEPOSIT = 'DEPOSIT', 'Поповнення'
        WITHDRAWAL = 'WITHDRAWAL', 'Зняття'
        BONUS = 'BONUS', 'Бонус'
        
    class Meta:
        verbose_name = 'Транзакція'
        verbose_name_plural = 'Транзакції'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['player', 'created_at']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['created_at']),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    game_session = models.ForeignKey(
        GameSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['player', 'created_at']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()}: {self.amount} грн - {self.player.user.username}"

    def save(self, *args, **kwargs):
        # Update player balance based on transaction type
        if not self.pk:  # Only on creation
            # Ensure amount is positive for all transaction types
            amount = abs(self.amount)
            
            # Set balance_after based on transaction type
            if self.transaction_type in [self.TransactionType.BET, self.TransactionType.WITHDRAWAL]:
                self.balance_after = self.player.balance - amount
                self.player.balance = self.balance_after
                self.amount = -amount  # Store as negative for withdrawals/bets
            else:  # WIN, DEPOSIT, BONUS
                self.balance_after = self.player.balance + amount
                self.player.balance = self.balance_after
                self.amount = amount  # Store as positive for deposits/wins
                
            # Update player's last activity
            self.player.updated_at = timezone.now()
            self.player.save(update_fields=['balance', 'updated_at'])
            
            # Update the player's balance
            self.balance_after = self.player.balance
        super().save(*args, **kwargs)



