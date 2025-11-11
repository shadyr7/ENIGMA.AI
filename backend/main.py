import uuid
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from deuces import Evaluator, Card as DeucesCard
from stable_baselines3 import PPO
import torch, os

from game_logic import PokerGame, GameState
from enigma_env_shaped import build_observation  # 134-dim obs + opp stats

# ================= FASTAPI SETUP =================
app = FastAPI()
origins = ["http://localhost", "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= GLOBALS =================
games = {}
evaluator = Evaluator()
rl_models = {}
MODEL_DIR = "models_enigma"
BIG_BLIND = 20


def evaluate_hand_strength(hand, board):
    rank_map = {r: i for i, r in enumerate("23456789TJQKA")}
    if not board:
        r1, r2 = rank_map[hand[0].rank], rank_map[hand[1].rank]
        score = max(r1, r2) + (min(r1, r2) / 10)
        if r1 == r2: score += 13
        if hand[0].suit == hand[1].suit: score += 2
        return min(score / 30, 1.0)

    deuces_board = [DeucesCard.new(c.rank + c.suit) for c in board]
    deuces_hand = [DeucesCard.new(c.rank + c.suit) for c in hand]
    score = evaluator.evaluate(deuces_board, deuces_hand)
    return 1.0 - (score / 7462.0)


def rule_bot(state: GameState):
    bot = next(p for p in state.players if p.id == 'bot')
    strength = evaluate_hand_strength(bot.hand, state.community_cards)
    to_call = max(0, state.current_bet_to_match - bot.current_bet)
    pot_now = state.pot + sum(p.current_bet for p in state.players)

    if strength > 0.8:
        return "raise", bot.current_bet + to_call + max(BIG_BLIND * 2, int(0.6 * max(pot_now, BIG_BLIND * 6)))
    if strength > 0.5:
        return ("call", 0) if to_call > 0 else ("check", 0)
    if to_call > max(BIG_BLIND, int(0.5 * max(pot_now, BIG_BLIND * 4))):
        return "fold", 0
    return ("check", 0)


def map_action(state: GameState, a: int):
    me = next(p for p in state.players if p.id == "bot")
    to_call = max(0, state.current_bet_to_match - me.current_bet)
    pot_now = state.pot + sum(p.current_bet for p in state.players)

    # Fold or check
    if a == 0:
        return ("fold", 0) if to_call > 0 else ("check", 0)

    # Call / check
    if a == 1:
        return ("call", 0) if to_call > 0 else ("check", 0)

    # Min-raise
    if a == 2:
        target = me.current_bet + to_call + max(20, 40)  # 2× big blind or call + 20
        return ("raise", target)

    # Pot-size raise
    if a == 3:
        max_raise = me.current_bet + to_call + int(pot_now)
        return ("raise", max_raise)

    # Big raise but capped
    if a == 4:
        max_raise = me.current_bet + to_call + int(0.75 * pot_now)
        return ("raise", max_raise)

    return ("check", 0)


# ================= LOAD MODEL AT STARTUP =================
@app.on_event("startup")
def load_models():
    print("✅ Loading trained RL models...")

    def pick_latest(prefix):
        cands = [f for f in os.listdir(MODEL_DIR) if f.startswith(prefix) and f.endswith(".zip")]
        if not cands:
            return None
        return sorted(cands, key=lambda x: int(x.split("_")[1].replace("k", "").replace(".zip", "")) if "k" in x else int(x.split("_")[1].replace(".zip", "")))[-1]

    newest = pick_latest("finalenigma_") or pick_latest("finenigma_")
    if not newest:
        print("⚠ No RL models found — RL disabled")
        return

    path = os.path.join(MODEL_DIR, newest)
    try:
        torch.set_default_dtype(torch.float32)
        model = PPO.load(path, device="cpu")
        rl_models["active"] = model
        print(f"✅ Loaded RL model: {newest}")
    except Exception as e:
        print(f"❌ Failed to load RL model {newest}", e)


# ================= REQUEST MODELS =================
class PlayerAction(BaseModel):
    action: str
    amount: int = 0

class NextHandPayload(BaseModel):
    user_chips: int
    bot_chips: int
    last_dealer_pos: int


# ================= CREATE GAME =================
@app.post("/api/game", response_model=GameState)
def create_game():
    game_id = str(uuid.uuid4())
    game = PokerGame(game_id=game_id)
    game.state.bot_model = "rl"
    games[game_id] = game
    return game.get_state()


# ================= NEXT HAND =================
@app.post("/api/game/next-hand", response_model=GameState)
def next_hand(payload: NextHandPayload):
    game_id = str(uuid.uuid4())
    game = PokerGame(
        game_id=game_id,
        user_chips=payload.user_chips,
        bot_chips=payload.bot_chips,
        dealer_pos=payload.last_dealer_pos,
    )
    game.state.bot_model = "rl"
    games[game_id] = game
    return game.get_state()


# ================= PLAYER ACTION =================
@app.post("/api/game/{game_id}/action", response_model=GameState)
def player_action(game_id: str, action: PlayerAction):
    game = games.get(game_id)
    if not game:
        raise HTTPException(404, "Game Not Found")

    if action.action != "none":
        game.handle_player_action("user", action.action, action.amount)

    # BOT LOOP
    while game.state.current_player_id == "bot" and not game.state.winner:
        state = game.state
        bot_player = next(p for p in state.players if p.id == "bot")

        if "active" in rl_models:
            try:
                obs, mask = build_observation(
                    state, pov="bot",
                    opp_stats={"agg": 0.3, "fold_freq": 0.3, "vpip": 0.3}
                )

                # ✅ dtype fix
                obs = obs.astype(np.float32)
                mask = mask.astype(np.int8)

                # ✅ SHAPE FIX — always batch
                if obs.ndim == 1:
                    obs = obs.reshape(1, -1)
                if mask.ndim == 1:
                    mask = mask.reshape(1, -1)

                dict_obs = {"observation": obs, "action_mask": mask}
                action_id, _ = rl_models["active"].predict(dict_obs, deterministic=False)
                action_id = int(action_id)

                # ✅ illegal fix
                if mask[0, action_id] == 0:
                    legal = np.where(mask[0] == 1)[0]
                    action_id = int(legal[0])

                verb, amt = map_action(state, action_id)

                print("\n===== RL MOVE =====")
                print("Stage:", state.current_stage)
                print("Bot:", [c.rank + c.suit for c in bot_player.hand])
                print("Pot:", state.pot)
                print("Action:", action_id, verb, amt)

            except Exception as e:
                print("\n❌ RL ERROR:", e)
                print("⚠️ Fallback to rule bot")
                verb, amt = rule_bot(state)
        else:
            verb, amt = rule_bot(state)

        game.handle_player_action("bot", verb, amt)

    return game.get_state()
