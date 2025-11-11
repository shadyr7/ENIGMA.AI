# enigma_env.py
import gymnasium as gym
import numpy as np
from gymnasium import spaces
from typing import Tuple, Dict, Any, Optional
from deuces import Evaluator, Card
from game_logic import PokerGame, GameState

ACTION_MEANINGS = ["fold", "check_call", "min_raise", "pot_raise", "all_in"]

def _stage_one_hot(stage: str) -> np.ndarray:
    stages = ["pre-flop", "flop", "turn", "river", "showdown"]
    vec = np.zeros(5, dtype=np.float32)
    if stage in stages:
        vec[stages.index(stage)] = 1.0
    return vec


def _rank_to_idx(r: str) -> int:
    return "23456789TJQKA".find(r)


def _card_to_vec(rank: str, suit: str) -> np.ndarray:
    rv = np.zeros(13, dtype=np.float32)
    sv = np.zeros(4, dtype=np.float32)
    if rank in "23456789TJQKA":
        rv[_rank_to_idx(rank)] = 1.0
    suits = {'s':0, 'h':1, 'd':2, 'c':3}
    if suit in suits:
        sv[suits[suit]] = 1.0
    return np.concatenate([rv, sv]).astype(np.float32)


def build_observation(state: GameState, pov: str = "bot"):
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

    dealer_vec = np.array([1.0 if state.players[state.dealer_position].id == pov else 0.0], dtype=np.float32)

    hole = np.zeros(34, dtype=np.float32)
    for i, c in enumerate(me.hand[:2]):
        hole[i*17:(i+1)*17] = _card_to_vec(c.rank, c.suit)

    board = np.zeros(85, dtype=np.float32)
    for i, c in enumerate(state.community_cards[:5]):
        board[i*17:(i+1)*17] = _card_to_vec(c.rank, c.suit)

    obs = np.concatenate([stage, nums, dealer_vec, hole, board]).astype(np.float32)

    legal = np.zeros(5, dtype=np.float32)
    to_call = max(0, state.current_bet_to_match - me.current_bet)
    legal[0] = 1.0 if to_call > 0 else 0.0
    legal[1] = 1.0

    if ("raise" in state.legal_actions) and (me.chips > to_call) and (state.winner is None):
        legal[2] = legal[3] = legal[4] = 1.0

    return obs.reshape(1, 131), legal.reshape(1, 5)


class EnigmaPokerEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, starting_chips: int = 10000, opponent: str = "rule_based"):
        super().__init__()
        self.starting_chips = starting_chips
        self.opponent_type = opponent
        self.observation_space = spaces.Dict({
            "observation": spaces.Box(low=-np.inf, high=np.inf, shape=(131,), dtype=np.float32),
            "action_mask": spaces.MultiBinary(5),
        })
        self.action_space = spaces.Discrete(5)

        self.game: Optional[PokerGame] = None
        self._raises: int = 0
        self._max_raises: int = 3
        self.evaluator = Evaluator()

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.game = PokerGame("training", starting_chips=self.starting_chips)
        self._raises = 0
        state = self.game.get_state()
        obs, mask = build_observation(state, pov="bot")
        return {"observation": obs, "action_mask": mask}, {}

    def step(self, action: int):
        state = self.game.get_state()

        # Opponent acts until it's bot's turn
        while state.current_player_id != "bot" and not state.winner:
            self._opponent_step()
            state = self.game.get_state()

        if state.winner:
            reward = self._terminal_reward(state)
            obs, mask = build_observation(state, pov="bot")
            return {"observation": obs, "action_mask": mask}, reward, True, False, {}

        act, amt = self._action_to_move(state, action)
        self.game.handle_player_action("bot", act, amt)

        # Opponent responses
        while self.game.get_state().current_player_id != "bot" and not self.game.get_state().winner:
            self._opponent_step()

        next_state = self.game.get_state()
        done = next_state.winner is not None
        reward = self._terminal_reward(next_state) if done else 0.0
        obs, mask = build_observation(next_state, pov="bot")
        return {"observation": obs, "action_mask": mask}, reward, done, False, {}

    def _evaluate_strength(self, hand, board):
        if not board:
            r = {r:i for i,r in enumerate("23456789TJQKA")}
            r1, r2 = r[hand[0].rank], r[hand[1].rank]
            s = max(r1,r2) + min(r1,r2)/10
            if hand[0].rank == hand[1].rank: s+=13
            if hand[0].suit == hand[1].suit: s+=2
            return min(s/30, 1.0)

        b = [Card.new(c.rank + c.suit) for c in board]
        h = [Card.new(c.rank + c.suit) for c in hand]
        score = self.evaluator.evaluate(b, h)
        return 1.0 - (score/7462)

    def _opponent_step(self):
        st = self.game.get_state()
        if st.winner:
            return

        opp = next(p for p in st.players if p.id != "bot")
        strength = self._evaluate_strength(opp.hand, st.community_cards)
        to_call = st.current_bet_to_match - opp.current_bet

        if strength > 0.8:
            move = ("raise", max(20, int(st.pot * 0.75)))
        elif strength > 0.5:
            move = ("call", 0)
        elif to_call > max(20, int(st.pot * 0.5)):
            move = ("fold", 0)
        else:
            move = ("check", 0)

        act, amt = move
        if act not in st.legal_actions:
            act = "check" if "check" in st.legal_actions else ("call" if "call" in st.legal_actions else "fold")
            amt = 0

        self.game.handle_player_action("user", act, amt)

    def _action_to_move(self, state, a):
        me = next(p for p in state.players if p.id == "bot")
        to_call = state.current_bet_to_match - me.current_bet
        pot = state.pot + sum(p.current_bet for p in state.players)
        can_raise = ("raise" in state.legal_actions) and me.chips > to_call and self._raises < self._max_raises

        if a == 0:
            return ("fold", 0) if to_call > 0 else ("check", 0)
        if a == 1:
            return ("call" if to_call > 0 else "check", 0)
        if a == 2 and can_raise:
            self._raises += 1
            return ("raise", max(state.current_bet_to_match*2, me.current_bet + to_call*2))
        if a == 3 and can_raise:
            self._raises += 1
            return ("raise", int(max(me.current_bet + to_call + pot, state.current_bet_to_match*2)))
        if a == 4 and can_raise:
            self._raises += 1
            return ("raise", me.current_bet + me.chips)

        return ("call" if to_call > 0 else "check", 0)

    def _terminal_reward(self, state):
        if state.winner == "bot":
            return 1.0
        if state.winner == "user":
            return -1.0
        return 0.0
