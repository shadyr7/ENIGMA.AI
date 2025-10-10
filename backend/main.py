# backend/main.py (Upgraded with a Smarter, Rule-Based Bot)
import random 
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
from pydantic import BaseModel

# Import our game logic and data models
from game_logic import PokerGame, GameState, Player
from deuces import Evaluator, Card as DeucesCard

app = FastAPI()

origins = [ "http://localhost", "http://localhost:3000" ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

games = {}
evaluator = Evaluator()

class PlayerAction(BaseModel):
    action: str
    amount: int = 0

class NextHandPayload(BaseModel):
    user_chips: int
    bot_chips: int
    last_dealer_pos: int 

def get_bot_action(state: GameState):
    """The 'Tough Bot' - Fights back against aggression. CORRECTED VERSION."""
    bot: Player = next(p for p in state.players if p.id == 'bot')
    user: Player = next(p for p in state.players if p.id == 'user')
    call_amount = state.current_bet_to_match - bot.current_bet

    # --- Pre-flop logic ---
    if state.current_stage == 'pre-flop':
        hand_ranks = {card.rank for card in bot.hand}

        # --- THE FIX IS HERE ---
        # If bot is dealer (small blind) and user hasn't raised yet, sometimes take initiative.
        is_bot_dealer = state.players[state.dealer_position].id == 'bot'
        if (
            is_bot_dealer 
            and state.current_bet_to_match == state.big_blind 
            and random.random() < 0.4  # 40% of the time
        ):
            print("Bot Logic: On the button, no raise. Taking initiative.")
            return "raise", state.big_blind * 3
        # --- END OF FIX ---

        # Premium hands always raise
        if {'A', 'K'} <= hand_ranks or {'Q', 'Q'} <= hand_ranks or {'J', 'J'} <= hand_ranks:
            print("Bot Logic: Premium hand pre-flop. Raising.")
            return "raise", user.current_bet * 3

        # Fold to very large pre-flop bets with a mediocre hand
        if call_amount > bot.chips * 0.2:
            print("Bot Logic: Mediocre hand and big bet pre-flop. Folding.")
            return "fold", 0

    # --- Post-flop logic ---
    # THE FIX: Only evaluate the hand if there are community cards.
    if state.community_cards:
        board = [DeucesCard.new(c.rank + c.suit) for c in state.community_cards]
        hand = [DeucesCard.new(c.rank + c.suit) for c in bot.hand]
        score = evaluator.evaluate(board, hand)

        # Very strong hand (Two pair or better) -> Be aggressive
        if score < 1600:
            print(f"Bot Logic: Strong hand (Score: {score}). Raising.")
            return "raise", state.pot * (0.75 + random.random())
        
        # Decent hand (One pair) -> Fight back sometimes
        elif score < 3325:
            if call_amount > 0 and random.random() < 0.25:  # 25% chance to re-raise
                print(f"Bot Logic: Decent hand (Score: {score}), re-raising.")
                return "raise", call_amount * 3
            else:
                print(f"Bot Logic: Decent hand (Score: {score}). Calling.")
                return "call", 0
        
        # Weak hand post-flop -> Fold to aggression
        else:
            if call_amount > 0 and random.random() < 0.8:  # 80% chance to fold to a bet
                print(f"Bot Logic: Weak hand (Score: {score}) and facing a bet. Folding.")
                return "fold", 0

    # --- Default fallback ---
    print("Bot Logic: Default action. Checking/Calling.")
    return "call", 0


@app.get("/api/health")
def read_root(): return {"status": "ok"}

@app.post("/api/game", response_model=GameState)
def create_game():
    game_id = str(uuid.uuid4())
    game = PokerGame(game_id=game_id)
    games[game_id] = game
    return game.get_state()

@app.get("/api/game/{game_id}", response_model=GameState)
def get_game_state(game_id: str):
    game = games.get(game_id)
    if not game: raise HTTPException(status_code=404, detail="Game not found")
    return game.get_state()

@app.post("/api/game/{game_id}/action", response_model=GameState)
def player_action(game_id: str, action: PlayerAction):
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    try:
        # Step 1: Handle the user's action.
        if action.action != "none": # A special action to allow the game to proceed when it's the bot's turn
            game.handle_player_action("user", action.action, action.amount)

        # Step 2: As long as it's the bot's turn and the hand isn't over, run the bot's logic.
        while game.state.current_player_id == "bot" and not game.state.winner:
            print("--- Bot's turn to act ---")
            bot_action, bot_amount = get_bot_action(game.state)
            game.handle_player_action("bot", bot_action, bot_amount)
            # This loop will continue if, for example, the bot checks and it's still its turn.
            # In our heads-up game, it will usually only run once.
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return game.get_state()



@app.post("/api/game/next-hand", response_model=GameState)
def next_hand(payload: NextHandPayload):
    """Starts a new hand with updated chip counts."""
    # This is a simplified approach; in a real app, you'd re-use the game_id
    game_id = str(uuid.uuid4())
    # We pass the current chip counts to the new game instance
    game = PokerGame(game_id=game_id, user_chips=payload.user_chips, bot_chips=payload.bot_chips)
    games[game_id] = game
    return game.get_state()