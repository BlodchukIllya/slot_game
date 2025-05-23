from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, models
from django.views.decorators.http import require_http_methods
from django.template import RequestContext
from django.http import HttpResponseNotFound
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from decimal import Decimal
import random
import json
from datetime import datetime, timedelta
from .models import Player, GameSession, Transaction

# Game constants
MIN_BET = Decimal('5.00')  # Lower minimum bet for better accessibility

# Payout multipliers for different win conditions
PAYOUTS = {
    'jackpot': Decimal('20.00'),  # 5 of a kind (rare but big win)
    'four_of_a_kind': Decimal('4.00'),  # 4 of a kind (good win)
    'three_of_a_kind': Decimal('1.50'),  # 3 of a kind (small win)
    'three_groups': Decimal('2.50'),  # 3 groups (2+2+1)
    'two_groups': Decimal('1.00'),  # 2 groups (3+2)
}

@require_http_methods(["GET"])
def index(request):
    if request.user.is_authenticated:
        return redirect('slot_game')
    return redirect('login')

@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect('slot_game')
        
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    # The Player model is automatically created by the signal
                    messages.success(request, 'Реєстрація успішна! Тепер ви можете увійти.')
                    return redirect('login')
            except Exception as e:
                messages.error(request, f'Помилка при створенні облікового запису: {str(e)}')
        else:
            # Add form errors to messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = UserCreationForm()
    
    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('slot_game')
        
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            return redirect('slot_game')
        else:
            messages.error(request, 'Неправильне ім\u0027я користувача або пароль. Будь ласка, спробуйте ще раз.')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})


def logout_view(request):
    auth_logout(request)
    return redirect('login')

@login_required
def slot_game(request):
    """Main game view"""
    # Get or create player profile if it doesn't exist
    player, created = Player.objects.get_or_create(
        user=request.user,
        defaults={'balance': Decimal('1000.00')}  # Default starting balance
    )
    
    # Get the latest game session if it exists
    latest_session = GameSession.objects.filter(player=player).order_by('-created_at').first()
    
    # If there's a previous game session, use its numbers
    if latest_session and latest_session.numbers:
        numbers = latest_session.numbers
        if isinstance(numbers, list):
            # Ensure we have exactly 5 numbers
            numbers = numbers[:5] if len(numbers) >= 5 else numbers + [7] * (5 - len(numbers))
        else:
            # If numbers is not a list, use default
            numbers = [7, 7, 7, 7, 7]
    else:
        numbers = [7, 7, 7, 7, 7]
    
    return render(request, 'slot.html', {
        'balance': player.balance,
        'min_bet': MIN_BET,
        'num1': numbers[0],
        'num2': numbers[1],
        'num3': numbers[2],
        'num4': numbers[3],
        'num5': numbers[4],
        'player': player
    })

@login_required
def play(request):
    """Handle game play with database transactions"""
    if request.method != 'POST':
        return redirect('slot_game')
    
    # Get or create player profile if it doesn't exist
    player, created = Player.objects.get_or_create(
        user=request.user,
        defaults={'balance': Decimal('1000.00')}
    )
    
    # Check if player has enough balance
    if player.balance < MIN_BET:
        messages.error(request, f"Недостатньо грошей для гри! Мінімальна ставка - {MIN_BET} грн.")
        return redirect('slot_game')
    
    # Start database transaction
    with transaction.atomic():
        # Create bet transaction
        bet_transaction = Transaction.objects.create(
            player=player,
            amount=MIN_BET,
            transaction_type=Transaction.TransactionType.BET,
            balance_after=player.balance - MIN_BET
        )
        
        # Update player balance
        player.balance -= MIN_BET
        player.save()
        
        # Generate game result
        game_result = generate_game_result()
        
        # Ensure we have exactly 5 numbers
        if not isinstance(game_result, list) or len(game_result) != 5:
            game_result = [7, 7, 7, 7, 7]
        
        # Determine win amount and result type
        win_amount = Decimal('0.00')
        result_type = GameSession.GameResult.LOSS
        
        if is_jackpot(game_result):
            win_amount = MIN_BET * PAYOUTS['jackpot']
            result_type = GameSession.GameResult.JACKPOT
        elif has_four_of_a_kind(game_result):
            win_amount = MIN_BET * PAYOUTS['four_of_a_kind']
            result_type = GameSession.GameResult.WIN
        elif has_three_of_a_kind(game_result):
            win_amount = MIN_BET * PAYOUTS['three_of_a_kind']
            result_type = GameSession.GameResult.WIN
        elif has_three_groups(game_result):
            win_amount = MIN_BET * PAYOUTS['three_groups']
            result_type = GameSession.GameResult.WIN
        elif has_two_groups(game_result):
            win_amount = MIN_BET * PAYOUTS['two_groups']
            result_type = GameSession.GameResult.WIN
        
        # Create game session
        game_session = GameSession.objects.create(
            player=player,
            bet_amount=MIN_BET,
            result=result_type,
            win_amount=win_amount,
            numbers=game_result
        )
        
        # Process win if any
        if win_amount > 0:
            # Create win transaction
            Transaction.objects.create(
                player=player,
                amount=win_amount,
                transaction_type=Transaction.TransactionType.WIN,
                game_session=game_session,
                balance_after=player.balance + win_amount
            )
            # Update player balance
            player.balance += win_amount
            # Update player statistics
            player.wins += 1
            player.save()
            message = f"Ви виграли {win_amount} грн!"
            is_win = True
        else:
            # Update player statistics
            player.losses += 1
            player.save()
            message = f"Спробуйте ще раз!"
            is_win = False
    
    # Prepare context for the template
    context = {
        'min_bet': MIN_BET,
        'num1': game_result[0],
        'num2': game_result[1],
        'num3': game_result[2],
        'num4': game_result[3],
        'num5': game_result[4],
        'message': message,
        'is_win': is_win,
        'player': player
    }
    
    return render(request, 'slot.html', context)

def generate_game_result():
    """Generate a random game result with 5 numbers from 1 to 7"""
    random_chance = random.randint(0, 999)
    
    if random_chance < 1:  # 0.1% chance for jackpot (5 of a kind)
        number = random.randint(1, 7)
        return [number] * 5
    elif random_chance < 10:  # 0.9% chance for 4 of a kind
        number = random.randint(1, 7)
        different_number = random.choice([x for x in range(1, 8) if x != number])
        result = [number] * 4 + [different_number]
        random.shuffle(result)
        return result
    elif random_chance < 40:  # 3.6% chance for 3 of a kind
        number = random.randint(1, 7)
        other_numbers = random.sample([x for x in range(1, 8) if x != number], 2)
        result = [number] * 3 + other_numbers
        random.shuffle(result)
        return result
    elif random_chance < 50:  # 1% chance for 3 groups (2+2+1)
        numbers = [random.randint(1, 7) for _ in range(3)]
        result = numbers[:2] * 2 + [numbers[2]]
        random.shuffle(result)
        return result
    elif random_chance < 60:  # 1% chance for 2 groups (3+2)
        numbers = [random.randint(1, 7) for _ in range(2)]
        result = [numbers[0]] * 3 + [numbers[1]] * 2
        random.shuffle(result)
        return result
    else:  # 94.4% chance for loss (all different or no winning pattern)
        return [random.randint(1, 7) for _ in range(5)]

def is_jackpot(numbers):
    """Check if all numbers are the same"""
    return len(set(numbers)) == 1

def has_four_of_a_kind(numbers):
    """Check if there are 4 identical numbers"""
    for num in set(numbers):
        if numbers.count(num) >= 4:
            return True
    return False

def has_three_groups(numbers):
    """Check for pattern with 3 groups (2+2+1)"""
    counts = {}
    for num in numbers:
        counts[num] = counts.get(num, 0) + 1
    sorted_counts = sorted(counts.values(), reverse=True)
    return len(sorted_counts) == 3 and sorted_counts[0] == 2 and sorted_counts[1] == 2

def has_three_of_a_kind(numbers):
    """Check if there are 3 identical numbers"""
    for num in set(numbers):
        if numbers.count(num) == 3:
            return True
    return False

def has_two_groups(numbers):
    """Check for pattern with 2 groups (3+2)"""
    counts = {}
    for num in numbers:
        counts[num] = counts.get(num, 0) + 1
    sorted_counts = sorted(counts.values(), reverse=True)
    return len(sorted_counts) == 2 and sorted_counts[0] == 3 and sorted_counts[1] == 2


@login_required
def game_history(request):
    """View to display user's game history"""
    player = get_object_or_404(Player, user=request.user)
    game_sessions = GameSession.objects.filter(player=player).order_by('-created_at').select_related('player')
    
    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(game_sessions, 10)  # 10 games per page
    
    try:
        game_sessions_page = paginator.page(page)
    except PageNotAnInteger:
        game_sessions_page = paginator.page(1)
    except EmptyPage:
        game_sessions_page = paginator.page(paginator.num_pages)
    
    return render(request, 'game_history.html', {
        'game_sessions': game_sessions_page,
        'player': player
    })


@login_required
def profile(request):
    """View to display user profile"""
    player = get_object_or_404(Player, user=request.user)
    
    # Get last 10 games
    recent_games = GameSession.objects.filter(player=player).order_by('-created_at')[:10]
    
    # Calculate statistics
    total_games = GameSession.objects.filter(player=player).count()
    total_wins = GameSession.objects.filter(player=player, result='WIN').count()
    total_jackpots = GameSession.objects.filter(player=player, result='JACKPOT').count()
    
    if total_games > 0:
        win_rate = (total_wins / total_games) * 100
    else:
        win_rate = 0
    
    return render(request, 'profile.html', {
        'player': player,
        'recent_games': recent_games,
        'total_games': total_games,
        'total_wins': total_wins,
        'total_jackpots': total_jackpots,
        'win_rate': win_rate
    })

@login_required
def get_player_stats(request):
    """Get player statistics for the chart"""
    player = get_object_or_404(Player, user=request.user)
    
    # Get games from the last 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)
    games = GameSession.objects.filter(
        player=player,
        created_at__gte=thirty_days_ago
    ).order_by('created_at')
    
    # Prepare data for the chart
    labels = []
    wins = []
    losses = []
    jackpots = []
    
    # Group games by day
    current_date = None
    win_count = 0
    loss_count = 0
    jackpot_count = 0
    
    for game in games:
        game_date = game.created_at.date()
        if game_date != current_date:
            if current_date:
                labels.append(current_date.strftime('%d.%m'))
                wins.append(win_count)
                losses.append(loss_count)
                jackpots.append(jackpot_count)
            current_date = game_date
            win_count = 0
            loss_count = 0
            jackpot_count = 0
            
        if game.result == 'WIN':
            win_count += 1
        elif game.result == 'LOSS':
            loss_count += 1
        elif game.result == 'JACKPOT':
            jackpot_count += 1
    
    # Add the last day's data
    if current_date:
        labels.append(current_date.strftime('%d.%m'))
        wins.append(win_count)
        losses.append(loss_count)
        jackpots.append(jackpot_count)
    
    return JsonResponse({
        'labels': labels,
        'datasets': [
            {
                'label': 'Виграші',
                'data': wins,
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'borderColor': 'rgba(75, 192, 192, 1)',
                'borderWidth': 1
            },
            {
                'label': 'Програші',
                'data': losses,
                'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                'borderColor': 'rgba(255, 99, 132, 1)',
                'borderWidth': 1
            },
            {
                'label': 'Джекпоти',
                'data': jackpots,
                'backgroundColor': 'rgba(255, 205, 86, 0.2)',
                'borderColor': 'rgba(255, 205, 86, 1)',
                'borderWidth': 1
            }
        ]
    })

def page_not_found(request, exception=None):
    """Custom 404 error handler"""
    return render(request, '404.html', status=404)
