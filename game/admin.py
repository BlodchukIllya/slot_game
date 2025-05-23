from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Sum, F, Case, When, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Player, GameSession, Transaction


class BalanceListFilter(admin.SimpleListFilter):
    title = 'баланс гравця'
    parameter_name = 'balance'

    def lookups(self, request, model_admin):
        return (
            ('0', 'Нульовий баланс'),
            ('positive', 'Позитивний баланс'),
            ('negative', 'Негативний баланс'),
            ('high_roller', 'Високі ставки (5000+ ₴)'),
        )

    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.filter(player__balance=0)
        elif self.value() == 'positive':
            return queryset.filter(player__balance__gt=0)
        elif self.value() == 'negative':
            return queryset.filter(player__balance__lt=0)
        elif self.value() == 'high_roller':
            return queryset.filter(player__balance__gte=5000)


class PlayerInline(admin.StackedInline):
    model = Player
    can_delete = False
    verbose_name_plural = 'Профіль гравця'
    fk_name = 'user'
    fields = ('balance', 'last_activity', 'total_games_played', 'total_won')
    readonly_fields = ('last_activity', 'total_games_played', 'total_won')


class PlayerAdmin(admin.ModelAdmin):
    list_display = ('user_username', 'balance_display', 'games_played', 'total_won_display', 'last_activity')
    list_filter = ('last_activity',)
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user_link', 'games_played', 'total_won', 'last_activity')
    fieldsets = (
        (None, {
            'fields': ('user_link', 'balance', 'last_activity')
        }),
        ('Статистика', {
            'fields': ('games_played', 'total_won'),
            'classes': ('collapse',)
        }),
    )

    def user_username(self, obj):
        return obj.user.username
    user_username.short_description = 'Користувач'
    user_username.admin_order_field = 'user__username'

    def balance_display(self, obj):
        color = 'green' if obj.balance >= 0 else 'red'
        return format_html('<span style="color: {};">{:.2f} ₴</span>', color, obj.balance)
    balance_display.short_description = 'Баланс'
    balance_display.admin_order_field = 'balance'

    def total_won_display(self, obj):
        return f"{obj.total_won:.2f} ₴"
    total_won_display.short_description = 'Всього виграно'
    total_won_display.admin_order_field = 'total_won'

    def games_played(self, obj):
        return obj.game_sessions.count()
    games_played.short_description = 'Ігор зіграно'

    def user_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.user.id])
        return mark_safe(f'<a href="{url}">{obj.user.username}</a>')
    user_link.short_description = 'Користувач'


class CustomUserAdmin(UserAdmin):
    inlines = (PlayerInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_balance', 'last_login')
    list_select_related = ('player', )
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    date_hierarchy = 'date_joined'

    def get_balance(self, instance):
        if hasattr(instance, 'player'):
            return f"{instance.player.balance:.2f} ₴"
        return "0.00 ₴"
    get_balance.short_description = 'Баланс'
    get_balance.admin_order_field = 'player__balance'

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)


class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    readonly_fields = ('transaction_type_display', 'amount_display', 'balance_after_display', 'created_at')
    fields = ('transaction_type_display', 'amount_display', 'game_session_link', 'balance_after_display', 'created_at')
    can_delete = False

    def transaction_type_display(self, obj):
        colors = {
            'BET': 'warning',
            'WIN': 'success',
            'BONUS': 'info',
            'DEPOSIT': 'primary'
        }
        color = colors.get(obj.transaction_type, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_transaction_type_display()
        )
    transaction_type_display.short_description = 'Тип'

    def amount_display(self, obj):
        color = 'success' if obj.amount >= 0 else 'danger'
        return format_html(
            '<span style="color: {};">{}{:.2f} ₴</span>',
            color, '+' if obj.amount >= 0 else '', obj.amount
        )
    amount_display.short_description = 'Сума'

    def balance_after_display(self, obj):
        return f"{obj.balance_after:.2f} ₴"
    balance_after_display.short_description = 'Баланс після'

    def game_session_link(self, obj):
        if obj.game_session:
            url = reverse('admin:game_gamesession_change', args=[obj.game_session.id])
            return mark_safe(f'<a href="{url}">Сесія #{obj.game_session.id}</a>')
        return "-"
    game_session_link.short_description = 'Гра'


class GameSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'player_link', 'bet_amount_display', 'result_display', 'win_amount_display', 'created_at')
    list_filter = ('result', 'created_at', BalanceListFilter)
    search_fields = ('player__user__username', 'id')
    readonly_fields = ('created_at', 'player_link', 'win_amount_display')
    inlines = [TransactionInline]
    date_hierarchy = 'created_at'
    list_per_page = 25
    save_on_top = True

    def player_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.player.user.id])
        return mark_safe(f'<a href="{url}">{obj.player.user.username}</a>')
    player_link.short_description = 'Гравець'
    player_link.admin_order_field = 'player__user__username'

    def bet_amount_display(self, obj):
        return f"{obj.bet_amount:.2f} ₴"
    bet_amount_display.short_description = 'Ставка'
    bet_amount_display.admin_order_field = 'bet_amount'

    def win_amount_display(self, obj):
        amount = float(obj.win_amount)
        amount_str = f"{amount:.2f}"
        if amount > 0:
            return format_html('<span style="color: green;">+{} ₴</span>', amount_str)
        return format_html('{} ₴', amount_str)
    win_amount_display.short_description = 'Виграш'
    win_amount_display.admin_order_field = 'win_amount'

    def result_display(self, obj):
        colors = {
            'WIN': 'success',
            'LOSS': 'danger',
            'DRAW': 'warning'
        }
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            colors.get(obj.result, 'secondary'),
            obj.get_result_display()
        )
    result_display.short_description = 'Результат'
    result_display.admin_order_field = 'result'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('player__user')


class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaction_type_display', 'player_link', 'amount_display', 'balance_after_display', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('player__user__username', 'id')
    readonly_fields = ('created_at', 'balance_after', 'player_link', 'game_session_link')
    date_hierarchy = 'created_at'
    list_per_page = 25
    save_on_top = True

    def transaction_type_display(self, obj):
        colors = {
            'BET': 'warning',
            'WIN': 'success',
            'BONUS': 'info',
            'DEPOSIT': 'primary'
        }
        color = colors.get(obj.transaction_type, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_transaction_type_display()
        )
    transaction_type_display.short_description = 'Тип'
    transaction_type_display.admin_order_field = 'transaction_type'

    def amount_display(self, obj):
        amount = float(obj.amount)
        color = 'success' if amount >= 0 else 'danger'
        sign = '+' if amount >= 0 else ''
        formatted_amount = f"{amount:.2f}"
        return format_html(
            '<span style="color: {};">{}{} ₴</span>',
            color, sign, formatted_amount
        )
    amount_display.short_description = 'Сума'
    amount_display.admin_order_field = 'amount'

    def balance_after_display(self, obj):
        return f"{obj.balance_after:.2f} ₴"
    balance_after_display.short_description = 'Баланс після'
    balance_after_display.admin_order_field = 'balance_after'

    def player_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.player.user.id])
        return mark_safe(f'<a href="{url}">{obj.player.user.username}</a>')
    player_link.short_description = 'Гравець'
    player_link.admin_order_field = 'player__user__username'

    def game_session_link(self, obj):
        if obj.game_session:
            url = reverse('admin:game_gamesession_change', args=[obj.game_session.id])
            return mark_safe(f'<a href="{url}">Сесія #{obj.game_session.id}</a>')
        return "-"
    game_session_link.short_description = 'Гра'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('player__user', 'game_session')


# Unregister the default User admin
admin.site.unregister(User)

# Register all models with their admin classes
admin.site.register(User, CustomUserAdmin)
admin.site.register(Player, PlayerAdmin)
admin.site.register(GameSession, GameSessionAdmin)
admin.site.register(Transaction, TransactionAdmin)
