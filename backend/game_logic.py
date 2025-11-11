# game_logic.py — final version with raise caps + sanity checks

import random
from deuces import Card as DeucesCard, Evaluator
from pydantic import BaseModel
from typing import List, Optional

MAX_RAISES_PER_ROUND = 3  # <-- hard cap per street
POT_SIZE_RAISE_MULTIPLIER = 1.0   # max allowed raise is 1x pot

class Card(BaseModel):
    rank: str
    suit: str

class Player(BaseModel):
    id: str
    chips: int
    hand: List[Card] = []
    current_bet: int = 0
    has_acted: bool = False
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
    raises_this_round: int = 0       # ✅ NEW
    small_blind: int = 10
    big_blind: int = 20
    dealer_position: int = 0
    bot_model: str = "rl"
    legal_actions: List[str] = []
    winner: Optional[str] = None

class PokerGame:
    def __init__(self, game_id: str, starting_chips: int = 10000, user_chips=None, bot_chips=None, dealer_pos=-1):
        self.evaluator = Evaluator()
        user_chips = user_chips or starting_chips
        bot_chips = bot_chips or starting_chips
        players = [Player(id="user", chips=user_chips), Player(id="bot", chips=bot_chips)]
        dealer_pos = dealer_pos if dealer_pos != -1 else random.randint(0, 1)

        self.state = GameState(
            game_id=game_id,
            players=players,
            current_stage="pre-flop",
            dealer_position=dealer_pos,
        )
        self._start_new_hand()

    def get_state(self):
        return self.state

    def _start_new_hand(self):
        # reset
        for p in self.state.players:
            p.hand = []
            p.current_bet = 0
            p.has_acted = False
            p.folded = False
            p.last_action = None

        self.state.community_cards = []
        self.state.pot = 0
        self.state.winner = None
        self.state.raises_this_round = 0   # ✅ reset

        # deck
        self.deck = [Card(rank=r, suit=s) for r in "23456789TJQKA" for s in "shdc"]
        random.shuffle(self.deck)

        sb = self.state.players[self.state.dealer_position]
        bb = self.state.players[1 - self.state.dealer_position]

        sb.hand = [self.deck.pop(), self.deck.pop()]
        bb.hand = [self.deck.pop(), self.deck.pop()]

        sb.chips -= self.state.small_blind
        sb.current_bet = self.state.small_blind
        bb.chips -= self.state.big_blind
        bb.current_bet = self.state.big_blind

        self.state.pot = sb.current_bet + bb.current_bet
        self.state.current_bet_to_match = self.state.big_blind
        self.state.current_player_id = sb.id

        self._update_legal_actions()

    def _get_player(self, pid):
        return next(p for p in self.state.players if p.id == pid)

    def _update_legal_actions(self):
        player = self._get_player(self.state.current_player_id)
        actions = ['fold']

        to_call = self.state.current_bet_to_match - player.current_bet
        if to_call > 0:
            actions.append("call")
        else:
            actions.append("check")

        # ✅ block raises if already raised too many times
        if self.state.raises_this_round < MAX_RAISES_PER_ROUND and player.chips > to_call:
            actions.append("raise")

        self.state.legal_actions = actions

    def handle_player_action(self, pid, action, amount=0):
        player = self._get_player(pid)
        other = self._get_player("bot" if pid == "user" else "user")
        player.has_acted = True
        to_call = self.state.current_bet_to_match - player.current_bet

        if action == "fold":
            player.folded = True
            player.last_action = "Fold"
            self._advance_turn()
            return

        # call/check
        if action in ("check", "call"):
            call_amt = max(0, to_call)
            call_amt = min(call_amt, player.chips)
            player.chips -= call_amt
            player.current_bet += call_amt
            self.state.pot += call_amt
            player.last_action = "Call" if call_amt > 0 else "Check"
            self._advance_turn()
            return

        # raise with HARD LIMITS
        if action == "raise":
            # ✅ enforce min raise = 2x big blind
            min_raise = max(self.state.big_blind, to_call * 2)

            # ✅ enforce max raise
            pot_now = self.state.pot + sum(p.current_bet for p in self.state.players)
            max_raise = int(min(player.current_bet + to_call + pot_now * POT_SIZE_RAISE_MULTIPLIER, player.current_bet + player.chips))

            # sanitize requested amount
            target = max(min_raise, amount)
            target = min(target, max_raise)

            # if target still below call, convert to call
            if target <= player.current_bet or target <= self.state.current_bet_to_match:
                return self.handle_player_action(pid, "call", 0)

            # execute
            add = target - player.current_bet
            player.chips -= add
            player.current_bet = target
            self.state.pot += add

            self.state.current_bet_to_match = player.current_bet
            self.state.last_raiser_id = pid
            self.state.raises_this_round += 1

            # force other to act again
            other.has_acted = False
            player.last_action = f"Raise to {player.current_bet}"

            self._advance_turn()
            return

    def _advance_turn(self):
        # someone folded
        alive = [p for p in self.state.players if not p.folded]
        if len(alive) == 1:
            self._finish_hand(alive[0].id)
            return

        # betting round over?
        if self._round_over():
            self._advance_stage()
            return

        # switch turn
        current = self.state.current_player_id
        self.state.current_player_id = "user" if current == "bot" else "bot"
        self._update_legal_actions()

    def _round_over(self):
        alive = [p for p in self.state.players if not p.folded]
        bets = [p.current_bet for p in alive]
        return all(p.has_acted for p in alive) and len(set(bets)) == 1

    def _advance_stage(self):
        stages = ["pre-flop", "flop", "turn", "river", "showdown"]
        idx = stages.index(self.state.current_stage)
        if idx == 3:
            self._finish_showdown()
            return

        # move bets into pot, reset
        for p in self.state.players:
            self.state.pot += p.current_bet
            p.current_bet = 0
            p.has_acted = False

        self.state.current_bet_to_match = 0
        self.state.last_raiser_id = None
        self.state.raises_this_round = 0     # ✅ reset raise counter
        self.state.current_stage = stages[idx + 1]

        # deal cards
        if self.state.current_stage == "flop":
            self.deck.pop()
            self.state.community_cards.extend([self.deck.pop(), self.deck.pop(), self.deck.pop()])
        elif self.state.current_stage in ["turn", "river"]:
            self.deck.pop()
            self.state.community_cards.append(self.deck.pop())

        # next actor
        self.state.current_player_id = self.state.players[self.state.dealer_position].id
        self._update_legal_actions()

    def _finish_showdown(self):
        user = self._get_player("user")
        bot = self._get_player("bot")
        board = [DeucesCard.new(c.rank + c.suit) for c in self.state.community_cards]

        user_score = self.evaluator.evaluate(board, [DeucesCard.new(c.rank + c.suit) for c in user.hand])
        bot_score = self.evaluator.evaluate(board, [DeucesCard.new(c.rank + c.suit) for c in bot.hand])

        total = self.state.pot + user.current_bet + bot.current_bet
        if user_score < bot_score:
            user.chips += total
            self.state.winner = "user"
        elif bot_score < user_score:
            bot.chips += total
            self.state.winner = "bot"
        else:
            user.chips += total // 2
            bot.chips += total // 2
            self.state.winner = "tie"

    def _finish_hand(self, winner_id):
        winner = self._get_player(winner_id)
        loser = self._get_player("bot" if winner_id=="user" else "user")
        pot_total = self.state.pot + winner.current_bet + loser.current_bet
        winner.chips += pot_total
        self.state.winner = winner_id
