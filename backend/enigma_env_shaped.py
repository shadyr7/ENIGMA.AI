# enigma_env_shaped.py — FINAL (capped raises, stronger shaping, smarter opponent)
import gymnasium as gym
import numpy as np
from gymnasium import spaces
from typing import Tuple, Dict, Any, Optional
from deuces import Evaluator, Card as DeucesCard

from game_logic import PokerGame, GameState

ACTION_MEANINGS = ["fold", "check_call", "min_raise", "pot_raise", "big_bet"]
_evaluator = Evaluator()

# Blinds & sizing constants
BIG_BLIND = 20
MAX_RAISES_PER_STREET = 3       # allow back-and-forth without going wild
MAX_RAISES_PER_HAND = 6            # hard cap per whole hand
MAX_RAISE_MULTI_POT = 2.0          # never size > 2x pot (hard cap)

# ---------------- Small helpers ----------------
def _rank_to_idx(r: str) -> int:
    return "23456789TJQKA".find(r)

def _card_to_vec(rank: str, suit: str) -> np.ndarray:
    rv = np.zeros(13, dtype=np.float32)
    sv = np.zeros(4, dtype=np.float32)
    if rank in "23456789TJQKA":
        rv[_rank_to_idx(rank)] = 1.0
    suits = {"s": 0, "h": 1, "d": 2, "c": 3}
    if suit in suits:
        sv[suits[suit]] = 1.0
    return np.concatenate([rv, sv], dtype=np.float32)

def _stage_one_hot(stage: str) -> np.ndarray:
    stages = ["pre-flop", "flop", "turn", "river", "showdown"]
    v = np.zeros(5, dtype=np.float32)
    if stage in stages:
        v[stages.index(stage)] = 1.0
    return v

def _hand_strength(hand, board) -> float:
    """0..1 (1 is best). Uses exact evaluator post-flop; reasonable preflop heuristic."""
    if not hand:
        return 0.0
    if not board:  # preflop heuristic
        rank_map = {r: i for i, r in enumerate("23456789TJQKA")}
        r1, r2 = rank_map[hand[0].rank], rank_map[hand[1].rank]
        score = max(r1, r2) + (min(r1, r2) / 10.0)
        if r1 == r2:
            score += 13
        if hand[0].suit == hand[1].suit:
            score += 2
        return float(min(score / 30.0, 1.0))

    deuces_board = [DeucesCard.new(c.rank + c.suit) for c in board]
    deuces_hand = [DeucesCard.new(c.rank + c.suit) for c in hand]
    raw = _evaluator.evaluate(deuces_board, deuces_hand)  # lower is better
    return float(1.0 - (raw / 7462.0))

def build_observation(state: GameState, pov="bot", opp_stats: Optional[Dict[str, float]] = None):
    """Returns (obs_vec, legal_mask) with shapes (134,), (5,)"""
    me = next(p for p in state.players if p.id == pov)
    opp = next(p for p in state.players if p.id != pov)

    stage = _stage_one_hot(state.current_stage)

    nums = np.array([
        state.pot,
        max(0, state.current_bet_to_match - me.current_bet),
        me.chips,
        opp.chips,
        me.current_bet,
        opp.current_bet,
    ], dtype=np.float32)

    dealer_is_me = 1.0 if state.players[state.dealer_position].id == pov else 0.0
    dealer_vec = np.array([dealer_is_me], dtype=np.float32)

    hole = np.zeros(34, dtype=np.float32)
    for i, c in enumerate(me.hand[:2]):
        hole[i * 17:(i + 1) * 17] = _card_to_vec(c.rank, c.suit)

    board = np.zeros(85, dtype=np.float32)
    for i, c in enumerate(state.community_cards[:5]):
        board[i * 17:(i + 1) * 17] = _card_to_vec(c.rank, c.suit)

    if opp_stats is None:
        opp_stats = {"agg": 0.0, "fold_freq": 0.0, "vpip": 0.0}
    opp_vec = np.array([
        float(opp_stats.get("agg", 0.0)),
        float(opp_stats.get("fold_freq", 0.0)),
        float(opp_stats.get("vpip", 0.0)),
    ], dtype=np.float32)

    obs = np.concatenate([stage, nums, dealer_vec, hole, board, opp_vec]).astype(np.float32)

    # action mask
    to_call = max(0, state.current_bet_to_match - me.current_bet)
    legal = np.zeros(5, dtype=np.float32)
    legal[0] = 1.0 if to_call > 0 else 0.0    # fold only if facing a bet
    legal[1] = 1.0                             # check/call always mapped
    can_raise = ("raise" in state.legal_actions) and (me.chips > to_call) and (state.winner is None)
    if can_raise:
        legal[2] = legal[3] = legal[4] = 1.0

    return obs, legal

# ---------------- Environment ----------------
class EnigmaPokerEnv(gym.Env):
    """
    FINAL: strong anti-overbet shaping, capped raises, tougher opponent that punishes leaks.
    """
    metadata = {"render_modes": []}

    def __init__(self, starting_chips=10000, opponent="balanced"):
        super().__init__()
        self.starting_chips = starting_chips
        self.opponent_type = opponent

        self.observation_space = spaces.Dict({
            "observation": spaces.Box(low=-np.inf, high=np.inf, shape=(134,), dtype=np.float32),
            "action_mask": spaces.MultiBinary(5),
        })
        self.action_space = spaces.Discrete(5)

        self.game: Optional[PokerGame] = None

        # raise tracking
        self._raises_this_street = 0
        self._opp_raises_this_street = 0
        self._max_raises = MAX_RAISES_PER_STREET

        self._total_raises_this_hand = 0
        self._actions_this_hand = []  # for diagnostics only

        self._last_action_type: Optional[str] = None
        self._last_raise_amount = 0
        self._last_street: Optional[str] = None

        # opponent stats (kept in env, not on GameState)
        self.opp_stats: Dict[str, float] = {"agg": 0.0, "fold_freq": 0.0, "vpip": 0.0}

    # ---------- helpers ----------
    def _reset_street_if_changed(self, st):
        if self._last_street != st:
            self._last_street = st
            self._raises_this_street = 0
            self._opp_raises_this_street = 0

    def _raise_amount_from_tier(self, state: GameState, tier: int, pov="bot") -> int:
        """
        Conservative raise sizing with hard caps:
          - tier 2 (min): ~ +2BB above to-call
          - tier 3 (pot): ~+0.6 * pot
          - tier 4 (big): ~+0.75 * pot
        And never exceed 2x pot or stack.
        """
        me = next(p for p in state.players if p.id == pov)
        to_call = max(0, state.current_bet_to_match - me.current_bet)
        pot_now = state.pot + sum(p.current_bet for p in state.players)

        min_bump = max(BIG_BLIND, to_call + BIG_BLIND)

        if tier == 2:
            target = me.current_bet + to_call + 2 * BIG_BLIND
            amt = max(target, me.current_bet + min_bump)

        elif tier == 3:
            target = me.current_bet + to_call + int(0.6 * max(pot_now, 3 * BIG_BLIND))
            amt = max(target, me.current_bet + min_bump)

        elif tier == 4:
            target = me.current_bet + to_call + int(0.75 * max(pot_now, 4 * BIG_BLIND))
            amt = max(target, me.current_bet + min_bump)

        else:
            amt = 0

        max_raise = min(
            me.current_bet + me.chips,  # stack cap
            me.current_bet + int(MAX_RAISE_MULTI_POT * max(pot_now, BIG_BLIND * 10))  # <= 2x pot
        )
        amt = int(min(amt, max_raise))
        if amt <= me.current_bet:
            amt = me.current_bet
        return amt

    # ---------- Gym API ----------
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.game = PokerGame(game_id="training", starting_chips=self.starting_chips)

        self._raises_this_street = 0
        self._opp_raises_this_street = 0
        self._total_raises_this_hand = 0
        self._actions_this_hand = []
        self._last_action_type = None
        self._last_raise_amount = 0
        self._last_street = None

        self.opp_stats = {"agg": 0.0, "fold_freq": 0.0, "vpip": 0.0}

        st = self.game.get_state()
        self._reset_street_if_changed(st.current_stage)
        obs, mask = build_observation(st, "bot", self.opp_stats)
        return {"observation": obs, "action_mask": mask}, {}

    def step(self, action: int):
        state = self.game.get_state()
        self._reset_street_if_changed(state.current_stage)

        # ensure it's our turn
        while state.current_player_id != "bot" and state.winner is None:
            self._opponent_step()
            state = self.game.get_state()
            self._reset_street_if_changed(state.current_stage)

        if state.winner is not None:
            return self._terminal_output(state)

        # do bot action
        verb, amount = self._action_to_move(state, action)
        self._last_action_type = verb
        self._last_raise_amount = amount if verb == "raise" else 0

        self._actions_this_hand.append((verb, amount, state.current_stage))
        if verb == "raise":
            self._total_raises_this_hand += 1

        self.game.handle_player_action("bot", verb, amount)

        # opponent reacts until our turn or terminal
        while self.game.get_state().current_player_id != "bot" and self.game.get_state().winner is None:
            self._opponent_step()

        next_state = self.game.get_state()
        self._reset_street_if_changed(next_state.current_stage)

        if next_state.winner is not None:
            return self._terminal_output(next_state)

        reward = self._nonterminal_shaping(state, next_state)
        obs, mask = build_observation(next_state, "bot", self.opp_stats)
        return {"observation": obs, "action_mask": mask}, float(reward), False, False, {}

    def _terminal_output(self, state: GameState):
        r = 1.0 if state.winner == "bot" else (-1.0 if state.winner == "user" else 0.0)
        obs, mask = build_observation(state, "bot", self.opp_stats)
        return {"observation": obs, "action_mask": mask}, float(r), True, False, {}

    # ---------- mapping ----------
    def _action_to_move(self, state: GameState, a: int) -> Tuple[str, int]:
        me = next(p for p in state.players if p.id == "bot")
        to_call = max(0, state.current_bet_to_match - me.current_bet)

        can_raise = (
            self._raises_this_street < self._max_raises
            and self._total_raises_this_hand < MAX_RAISES_PER_HAND
            and ("raise" in state.legal_actions)
            and me.chips > to_call
        )

        if a == 0:
            return ("fold", 0) if to_call > 0 else ("check", 0)
        if a == 1:
            return ("call" if to_call > 0 else "check", 0)

        if a in (2, 3, 4) and can_raise:
            amt = self._raise_amount_from_tier(state, a)
            if amt > me.current_bet:
                self._raises_this_street += 1
                return ("raise", amt)

        return ("call" if to_call > 0 else "check", 0)

    # ---------- opponent (tougher, punishes overbets) ----------
    def _opponent_step(self):
        st = self.game.get_state()
        if st.winner is not None:
            return

        user = next(p for p in st.players if p.id == "user")
        to_call = max(0, st.current_bet_to_match - user.current_bet)
        pot_now = st.pot + sum(p.current_bet for p in st.players)
        rand = np.random.rand()

        if to_call == 0:
            # probe sometimes
            if rand < 0.15:
                bump = max(BIG_BLIND * 2, int(0.4 * max(pot_now, BIG_BLIND * 4)))
                act, amt = "raise", min(user.current_bet + bump, user.current_bet + user.chips)
                self.opp_stats["agg"] += 0.02
            else:
                act, amt = "check", 0

        else:
            price = to_call / max(pot_now + to_call, 1)
            # punish huge bets
            if to_call > pot_now * 0.8:
                if rand < 0.50:
                    if rand < 0.25:
                        bump = max(BIG_BLIND * 3, int(0.7 * max(pot_now, BIG_BLIND * 8)))
                        act, amt = "raise", min(user.current_bet + to_call + bump, user.current_bet + user.chips)
                        self.opp_stats["agg"] += 0.04
                    else:
                        act, amt = "call", 0
                        self.opp_stats["vpip"] += 0.03
                else:
                    act, amt = "fold", 0
                    self.opp_stats["fold_freq"] += 0.02
            elif to_call > user.chips * 0.85:
                if rand < 0.65:
                    act, amt = "fold", 0
                    self.opp_stats["fold_freq"] += 0.03
                else:
                    act, amt = "call", 0
                    self.opp_stats["vpip"] += 0.02
            elif price < 0.25:
                if rand < 0.85:
                    act, amt = "call", 0
                    self.opp_stats["vpip"] += 0.02
                else:
                    bump = max(BIG_BLIND * 2, int(0.5 * max(pot_now, BIG_BLIND * 6)))
                    act, amt = "raise", min(user.current_bet + to_call + bump, user.current_bet + user.chips)
                    self.opp_stats["agg"] += 0.03
            else:
                if rand < 0.25:
                    bump = max(BIG_BLIND * 2, int(0.6 * max(pot_now, BIG_BLIND * 6)))
                    act, amt = "raise", min(user.current_bet + to_call + bump, user.current_bet + user.chips)
                    self.opp_stats["agg"] += 0.03
                elif rand < 0.50:
                    act, amt = "call", 0
                    self.opp_stats["vpip"] += 0.01
                else:
                    act, amt = "fold", 0
                    self.opp_stats["fold_freq"] += 0.015

        self.game.handle_player_action("user", act, amt)
        for k in self.opp_stats:
            self.opp_stats[k] = float(np.clip(self.opp_stats[k], 0.0, 1.0))

    # ---------- shaping (STRONGER) ----------
    def _nonterminal_shaping(self, prev: GameState, cur: GameState) -> float:
        """
        Strong penalties vs. overbetting; gentle rewards for good value & pot control.
        No blanket reward for 'raise' anymore.
        """
        me_prev = next(p for p in prev.players if p.id == "bot")
        reward = 0.0

        # only care if we raised
        if self._last_action_type != "raise" or self._last_raise_amount <= 0:
            # small pot-control incentive (occasionally) for strong hands
            s = _hand_strength(me_prev.hand, prev.community_cards)
            if self._last_action_type in ("check", "call") and s > 0.7 and prev.current_stage in ("flop", "turn", "river"):
                if np.random.rand() < 0.3:
                    reward += 0.01
            return float(reward)

        strength = _hand_strength(me_prev.hand, prev.community_cards)
        prev_pot_like = prev.pot + sum(p.current_bet for p in prev.players)
        prev_pot_like = max(prev_pot_like, BIG_BLIND * 4)  # avoid div-by-small
        raise_size = self._last_raise_amount - me_prev.current_bet

        # severe overbet penalties
        if prev.current_stage == "pre-flop":
            bb_mult = raise_size / max(BIG_BLIND, 1)
            if bb_mult > 12:
                reward -= 0.15
            elif bb_mult > 8:
                reward -= 0.08
            elif bb_mult > 6:
                reward -= 0.04
            if strength < 0.7 and bb_mult > 6:
                reward -= 0.10
        else:
            pot_multiple = raise_size / prev_pot_like
            if pot_multiple > 2.0:
                reward -= 0.12
            elif pot_multiple > 1.2:
                reward -= 0.06
            elif pot_multiple > 0.8:
                reward -= 0.03
            if strength < 0.5 and pot_multiple > 0.8:
                reward -= 0.10

            # modest reward for *moderate* value betting when strong
            if strength > 0.8 and 0.3 < pot_multiple < 0.8:
                reward += 0.015

        # penalty for spam-raising within a hand
        if self._total_raises_this_hand > 4:
            reward -= 0.08 * (self._total_raises_this_hand - 4)

        return float(reward)
