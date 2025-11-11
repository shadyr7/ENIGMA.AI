# ♠ ENIGMA: A Reinforcement Learning Texas Hold’em Poker AI

ENIGMA is a full-stack poker engine where a human player competes against a Reinforcement Learning–trained Texas Hold’em bot. The system integrates a FastAPI backend for the game engine and RL inference, a Next.js frontend for real-time gameplay, and a Stable-Baselines3 PPO RL model trained in a custom Gymnasium poker environment. The entire system is containerized using Docker for easy deployment.

---

## Features

| Component | Status | Description |
|---|---|---|
| Poker Game Engine | Complete | Fully custom Texas Hold’em logic, including betting, blinds, showdown, and pot distribution. |
| Reinforcement Learning Bot | Integrated | A Proximal Policy Optimization (PPO) agent trained on self-play using a custom environment. |
| Reward Shaping | Active | The reward function penalizes unrealistic betting while rewarding value bets and pot control. |
| Rule-Based Fallback Bot | Yes | A rule-based bot is utilized if the RL model is unavailable or encounters errors. |
| Frontend UI | Built | A real-time poker interface developed with Next.js. |
| Docker Support | Working | The entire system can be run with a single command using Docker Compose. |

---

## System Architecture

**Frontend (Next.js)**
*   Displays cards, actions, pot, and chip stacks.
*   Communicates with the backend via a REST API.
*   Dockerized as a separate container for independent operation.

**Backend (FastAPI)**
*   Manages the game state and logic.
*   Executes decisions from the Reinforcement Learning agent.
*   Loads the pre-trained PPO model from the `models_enigma/` directory.
*   Includes a rule-based bot as a fallback if the RL model is not found.

**Reinforcement Learning Engine**
*   Features a custom Gymnasium environment named `EnigmaPokerEnv`.
*   The action space consists of: fold, check/call, min-raise, pot-raise, and big-bet.
*   Utilizes a 134-dimensional state vector to represent the game state.
*   Employs strong reward shaping to prevent undesirable behaviors like persistent all-in bets.

---

## Project Structure

```
enigma/
│── backend/
│ ├── main.py # FastAPI routes and RL inference
│ ├── game_logic.py # Full poker rules
│ ├── enigma_env_shaped.py # Training environment
│ ├── train_selfplay_cycle.py # Script for training the RL model
│ └── models_enigma/ # Directory for trained models
│
│── frontend/
│ └── # Next.js poker client
│
├── training_v2/ # Optional directory for training scripts and logs
├── docker-compose.yml
└── README.md
```

---

## Requirements

### Backend
*   Python 3.10
```shell
pip install -r backend/requirements.txt
```

### Frontend
```shell
cd frontend
npm install
```

### Docker (recommended)
*   Docker Desktop or Docker Engine

---

## How to Run (Easiest – using Docker)

In the project root:
```yaml
docker-compose up --build
```

This will:
- Start the backend on **http://localhost:8000**
- Start the frontend on **http://localhost:3000**
- Load the RL model automatically (if present)

---

## How to Run Without Docker

### 1. Run backend
```shell
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Run frontend
```shell
cd frontend
npm start
```

---

## Playing Against the RL Bot

- The frontend shows cards and action buttons (Fold / Call / Raise).
- Every action triggers a `POST` request to `/api/game/{id}/action`.
- The RL bot returns its move, determined by the PPO model.
- If the RL model fails, the system automatically switches to the rule-based bot.

---

## Trained Models

A few selected models should be placed in the following directory:
```
backend/models_enigma/
├── finalenigma_500k.zip
└── finalenigma_1200k.zip
```

---

## What Is Not Included on GitHub

- Gigantic datasets
- Very large Tensorboard runs
- Model checkpoints > hundreds of MB
- Full experiment logs

These can be shared via Google Drive, Git LFS, or the HuggingFace Model Hub.

---

## Future Work

- Add multi-persona bots: tight, loose-aggressive, nit, calling-station.
- Implement player accounts and an Elo ranking system.
- Introduce persistent chip stacks and leaderboards.
- Add an LLM personality layer for funny trash-talk and move explanations.
- Use WebSockets for real-time betting animations.
- Develop multi-player tables (4–6 seats).
- Integrate Game Theory Optimal (GTO) strategies.
- Build a fully functional and aesthetic UI/backend with user login, sign-up, game history, and the ability to play against Enigma and other bots.

---

# ♠ Play Smart. Learn Poker. Try to beat Enigma.
In the words of one of the best ever wordsmiths and  GOAT, **Dwayne Michael Carter Jr.**, also known professionally as **Lil Wayne**:
**"So misunderstood but what's the world without Enigma?"**

