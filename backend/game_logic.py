# backend/game_logic.py
import random
from deuces import Card as DeucesCard, Evaluator
from pydantic import BaseModel
from typing import List, Optional

# --- Data Models ---

class Card(BaseModel):
    rank: str
    suit: str

class Player(BaseModel):
    id: str
    chips: int
    hand: List[Card] = []
    current_bet: int = 0
    has_acted: bool = False
    is_all_in: bool = False
    folded: bool = False
    last_action: Optional[str] = None

class GameState(BaseModel):
    game_id: str
    players: List[Player]
    community_cards: List[Card] = []
    pot: int = 0
    current_stage: str
    current_player_id: Optional[str] = None
    current_bet_to_match: int = 0
    last_raiser_id: Optional[str] = None
    small_blind: int = 10
    big_blind: int = 20
    dealer_position: int = 0
    winner: Optional[str] = None
    game_over: bool = False

# --- Game Engine ---

class PokerGame:
    def __init__(self, game_id: str, starting_chips: int = 10000, user_chips: Optional[int] = None, bot_chips: Optional[int] = None, dealer_pos: int = -1):
        ranks = "23456789TJQKA"
        suits = "shdc"
        self.deck = [Card(rank=r, suit=s) for r in ranks for s in suits]
        random.shuffle(self.deck)

        user_start_chips = user_chips if user_chips is not None else starting_chips
        bot_start_chips = bot_chips if bot_chips is not None else starting_chips
        
        players = [
            Player(id="user", chips=user_start_chips),
            Player(id="bot", chips=bot_start_chips),
        ]

        # On a brand new game, dealer is random. Otherwise, it's passed from the previous hand.
        initial_dealer = dealer_pos if dealer_pos != -1 else random.randint(0, 1)

        self.state = GameState(
            game_id=game_id,
            players=players,
            current_stage="pre-flop",
            small_blind=10,
            big_blind=20,
            dealer_position=initial_dealer
        )
        self._start_new_hand()

    def get_state(self):
        return self.state

    def _start_new_hand(self):
        # On the very first hand of a game, we don't rotate the dealer. On all subsequent hands, we do.
        if self.state.pot > 0:
             self.state.dealer_position = (self.state.dealer_position + 1) % len(self.state.players)

        for player in self.state.players:
            player.hand = []
            player.current_bet = 0
            player.has_acted = False
            player.is_all_in = False
            player.folded = False
            player.last_action = None
        
        self.state.community_cards = []
        self.state.pot = 0
        self.state.winner = None
        
        self.deck = [Card(rank=r, suit=s) for r in "23456789TJQKA" for s in "shdc"]
        random.shuffle(self.deck)

        # Assign roles based on the dealer position
        sb_player = self.state.players[self.state.dealer_position]
        bb_player = self.state.players[(self.state.dealer_position + 1) % len(self.state.players)]

        print(f"--- New Hand --- Dealer is {sb_player.id}. Small Blind is {sb_player.id}, Big Blind is {bb_player.id}.")

        # Deal cards
        sb_player.hand = [self.deck.pop(), self.deck.pop()]
        bb_player.hand = [self.deck.pop(), self.deck.pop()]
        
        # Post blinds
        sb_player.chips -= self.state.small_blind
        sb_player.current_bet = self.state.small_blind
        
        bb_player.chips -= self.state.big_blind
        bb_player.current_bet = self.state.big_blind
        
        self.state.pot = self.state.small_blind + self.state.big_blind
        self.state.current_bet_to_match = self.state.big_blind
        self.state.current_stage = "pre-flop"
        
        # First to act is always the player in the SB position
        self.state.current_player_id = sb_player.id
        self.state.last_raiser_id = bb_player.id

    def _get_player(self, player_id: str) -> Player:
        for p in self.state.players:
            if p.id == player_id:
                return p
        raise ValueError(f"Player with id {player_id} not found.")

    def _advance_turn(self):
        # If a player folded, the other one wins immediately.
        active_players = [p for p in self.state.players if not p.folded]
        if len(active_players) == 1:
            self.state.current_stage = "showdown" # End the hand
            self._determine_winner()
            return
        
        current_index = self.state.players.index(self._get_player(self.state.current_player_id))
        next_index = (current_index + 1) % len(self.state.players)
        self.state.current_player_id = self.state.players[next_index].id

    def _is_betting_round_over(self):
        active_players = [p for p in self.state.players if not p.folded]
        if len(active_players) <= 1: return True
        
        first_active_player_bet = next((p.current_bet for p in self.state.players if not p.folded), 0)
        
        all_acted = all(p.has_acted for p in active_players)
        all_bets_equal = all(p.current_bet == first_active_player_bet for p in active_players)

        # Big blind option check
        bb_player_index = (self.state.dealer_position + 1) % len(self.state.players)
        bb_player = self.state.players[bb_player_index]
        is_bb_option = (
            self.state.current_bet_to_match == self.state.big_blind and
            self.state.current_player_id == bb_player.id and
            not bb_player.has_acted
        )
        
        return all_acted and all_bets_equal and not is_bb_option

    def _advance_stage(self):
        stages = ["pre-flop", "flop", "turn", "river", "showdown"]
        current_stage_index = stages.index(self.state.current_stage)

        if current_stage_index >= len(stages) - 1:
            self.state.game_over = True
            return

        for player in self.state.players:
            if not player.folded:
                player.has_acted = False
                player.current_bet = 0
        
        self.state.current_bet_to_match = 0
        
        # Post-flop, SB (dealer) acts first
        self.state.current_player_id = self.state.players[self.state.dealer_position].id
        self.state.last_raiser_id = None
        
        next_stage = stages[current_stage_index + 1]
        self.state.current_stage = next_stage

        if next_stage == "flop":
            self.deck.pop() # Burn
            self.state.community_cards.extend([self.deck.pop(), self.deck.pop(), self.deck.pop()])
        elif next_stage in ["turn", "river"]:
            self.deck.pop() # Burn
            self.state.community_cards.append(self.deck.pop())
        elif next_stage == "showdown":
            self._determine_winner()

    def _determine_winner(self):
        evaluator = Evaluator()
        
        user = self._get_player("user")
        bot = self._get_player("bot")
        
        if user.folded:
            self.state.winner = bot.id
            bot.chips += self.state.pot
            return
        if bot.folded:
            self.state.winner = user.id
            user.chips += self.state.pot
            return

        board = [DeucesCard.new(c.rank + c.suit) for c in self.state.community_cards]
        user_hand = [DeucesCard.new(c.rank + c.suit) for c in user.hand]
        bot_hand = [DeucesCard.new(c.rank + c.suit) for c in bot.hand]
        
        user_score = evaluator.evaluate(board, user_hand)
        bot_score = evaluator.evaluate(board, bot_hand)
        
        if user_score < bot_score:
            self.state.winner = user.id
            user.chips += self.state.pot
        elif bot_score < user_score:
            self.state.winner = bot.id
            bot.chips += self.state.pot
        else:
            self.state.winner = "tie"
            user.chips += self.state.pot // 2
            bot.chips += self.state.pot // 2

    def handle_player_action(self, player_id: str, action: str, amount: int = 0):
        player = self._get_player(player_id)
        if player.id != self.state.current_player_id:
            raise ValueError("Not your turn to act.")

        other_player = self._get_player("bot" if player_id == "user" else "user")
        other_player.last_action = None

        if action == "fold":
            player.folded = True
            player.last_action = "Fold"
        
        elif action == "call":
            amount_to_call = self.state.current_bet_to_match - player.current_bet
            if amount_to_call > 0:
                player.last_action = "Call"
            else:
                player.last_action = "Check"

            if amount_to_call > player.chips: amount_to_call = player.chips
            player.chips -= amount_to_call
            player.current_bet += amount_to_call
            self.state.pot += amount_to_call
            player.has_acted = True
            
        elif action == "raise":
            min_raise = self.state.current_bet_to_match * 2
            if amount < min_raise: amount = min_raise
            if amount > player.chips + player.current_bet: amount = player.chips + player.current_bet

            amount_to_add = amount - player.current_bet
            player.chips -= amount_to_add
            player.current_bet += amount_to_add
            self.state.pot += amount_to_add
            
            self.state.current_bet_to_match = player.current_bet
            self.state.last_raiser_id = player.id
            
            for p in self.state.players:
                if p.id != player.id:
                    p.has_acted = False
            
            player.has_acted = True
            player.last_action = f"Raise to ${player.current_bet}"
        
        self._advance_turn()
        
        if self._is_betting_round_over():
            self._advance_stage()