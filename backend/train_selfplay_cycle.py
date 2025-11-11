# train_selfplay_cycle.py — FINAL (resumes from latest, stronger PPO settings, finalenigma_* naming)
import os
from typing import Optional, Tuple

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback

from enigma_env_shaped import EnigmaPokerEnv

SAVE_DIR = "models_enigma"
TB_DIR = "tb_enigma"
EVAL_DIR = "eval_logs"

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(TB_DIR, exist_ok=True)
os.makedirs(EVAL_DIR, exist_ok=True)

# training plan
NUM_ENVS = 8
CYCLES = 5                 # ≈ 500k more by default
TOTAL_ADD_STEPS = 100_000  # per cycle

# preferred resumes (first found is used)
PREFERRED_RESUME = [
    "finenigma_1000k.zip",   # latest fine model
    "plsenigma_800000.zip",  # earlier fine model
]

def make_env(seed=None):
    def _thunk():
        env = EnigmaPokerEnv(starting_chips=10000, opponent="balanced")
        if seed is not None:
            env.reset(seed=seed)
        return env
    return _thunk

def _find_resume_file() -> Optional[Tuple[str, int]]:
    """
    Return (path, steps_in_name) for the first existing preferred file.
    Steps are parsed so save names continue from where you left off.
    """
    for name in PREFERRED_RESUME:
        path = os.path.join(SAVE_DIR, name)
        if os.path.isfile(path):
            # parse 1000k / 800000
            num = 0
            base = os.path.splitext(os.path.basename(name))[0]
            # accept patterns like finenigma_1000k or plsenigma_800000
            import re
            m = re.search(r"(\d+)(k)?", base)
            if m:
                n, k = m.groups()
                num = int(n) * (1000 if k == "k" else 1)
            return path, num
    return None

def load_or_build():
    vec_env = DummyVecEnv([make_env(42 + i) for i in range(NUM_ENVS)])

    resume = _find_resume_file()
    if resume:
        path, steps = resume
        print(f"✅ Resuming from {path}")
        model = PPO.load(path, env=vec_env, device="auto")
        return model, vec_env, steps

    print("✅ Starting NEW model with improved hyperparameters")
    model = PPO(
        "MultiInputPolicy",
        vec_env,
        # ---- improved, stabler config ----
        ent_coef=0.02,           # more exploration (prevents collapse)
        target_kl=0.02,          # stop massive jumps
        n_steps=4096,            # larger rollout for steadier grads
        batch_size=512,          # smaller batches, more updates
        gamma=0.995,             # slightly longer horizon
        gae_lambda=0.98,         # smoother advantages
        n_epochs=6,              # a bit more optimization per batch
        learning_rate=1e-4,      # lower LR = stability
        clip_range=0.15,         # tighter PPO clip
        clip_range_vf=0.2,
        max_grad_norm=0.5,
        vf_coef=0.5,
        tensorboard_log=TB_DIR,
        device="auto",
        verbose=1,
    )
    return model, vec_env, 0

def save_tag_for(step_total: int) -> str:
    # final naming: finalenigma_XXk.zip
    k = step_total // 1000
    return f"finalenigma_{k}k.zip"

def main():
    set_random_seed(42)

    model, vec_env, start_steps = load_or_build()
    current_steps = start_steps

    # eval env + callbacks
    eval_env = DummyVecEnv([make_env(999)])
    checkpoint_cb = CheckpointCallback(
        save_freq=25_000,
        save_path=SAVE_DIR,
        name_prefix="checkpoint_finalenigma",
        save_replay_buffer=False,
        save_vecnormalize=True,
    )
    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=SAVE_DIR,
        log_path=EVAL_DIR,
        eval_freq=10_000,
        deterministic=True,
        render=False,
        n_eval_episodes=20,
    )

    print(f"🔹 Starting training at {current_steps} total steps")
    print(f"🔹 Training for {CYCLES} cycles × {TOTAL_ADD_STEPS} steps (≈ {CYCLES * TOTAL_ADD_STEPS:,})")
    print(f"🔹 Using {NUM_ENVS} parallel envs")

    for i in range(1, CYCLES + 1):
        print(f"\n🚀 Training cycle {i}/{CYCLES}")
        model.learn(
            total_timesteps=TOTAL_ADD_STEPS,
            progress_bar=True,
            callback=[checkpoint_cb, eval_cb],
            reset_num_timesteps=False,
        )
        current_steps += TOTAL_ADD_STEPS
        tag = save_tag_for(current_steps)
        out_path = os.path.join(SAVE_DIR, tag)
        model.save(out_path)
        print(f"✅ Saved model: {out_path}  (total steps={current_steps:,})")

    vec_env.close()
    eval_env.close()
    print("✅ Training complete.")

if __name__ == "__main__":
    main()
