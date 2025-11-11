# train_selfplay.py
import os
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.utils import set_random_seed
from enigma_env import EnigmaPokerEnv

SAVE_DIR = "models_enigma"
TB_DIR = "tb_enigma"

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(TB_DIR, exist_ok=True)

def make_env(seed=None):
    def _thunk():
        env = EnigmaPokerEnv(starting_chips=10000, opponent="rule_based")
        if seed is not None:
            env.reset(seed=seed)
        return env
    return _thunk

def main():
    print("✅ Creating training environment...")
    set_random_seed(42)

    # Multi-env training (4 parallel environments)
    env = DummyVecEnv([make_env(42) for _ in range(4)])

    # ✅ If GPU is available, Stable Baselines will use it:
    model = PPO(
        "MultiInputPolicy",
        env,
        verbose=1,
        tensorboard_log=TB_DIR,
        n_steps=2048,
        batch_size=2048,
        gae_lambda=0.95,
        n_epochs=4,
        gamma=0.99,
        learning_rate=3e-4,
        clip_range=0.2,
        device="auto"    # ✅ This allows GPU usage automatically
    )

    total_steps = 300_000  # you can increase later
    save_interval = 100_000

    for step in range(0, total_steps, save_interval):
        print(f"🚀 Training next {save_interval} steps...")
        model.learn(total_timesteps=save_interval, progress_bar=True)

        tag = f"enigma_{(step + save_interval)//1000}k"
        model.save(os.path.join(SAVE_DIR, tag))
        print(f"✅ Saved model: {tag}")

    env.close()
    print("✅ Training completed.")

if __name__ == "__main__":
    main()
