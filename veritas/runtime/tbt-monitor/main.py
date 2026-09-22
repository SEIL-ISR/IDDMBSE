from pathlib import Path
import numpy as np
import argparse

import gymnasium as gym
from gymnasium import Wrapper
import panda_gym
from moviepy.editor import *

from sb3_contrib import TQC

from tbt_monitor import *
from panda_specifications import *

here = Path(__file__).resolve().parent


class STLMonitorWrapper(Wrapper):

    def __init__(self, env):
        super().__init__(env)

    def reset(self, *, seed=None, options=None):
        self.traj = []
        self.sim_teps_elapsed = 0
        self.tbt = compose_seq(evaluate_reach_object, evaluate_grasp, evaluate_reach_goal)
        return super().reset(seed=seed, options=options)

    def get_signals(self, state, info):
        obs = state['observation']
        achieved_goal = state['achieved_goal']
        desired_goal = state['desired_goal']
        d2goal = np.linalg.norm(achieved_goal - desired_goal)

        ee_pos = obs[:3]
        obj_pos = obs[7:10]
        d2obj = np.linalg.norm(ee_pos - obj_pos)

        grasp = obs[6]

        signals = [d2obj, grasp, d2goal, info['is_success']]
        return signals

    def step(self, action):
        obs, _, terminated, truncated, info = self.env.step(action)
        signals = self.get_signals(obs, info)
        self.traj.append(signals)
        self.sim_teps_elapsed += 1
        if self.sim_teps_elapsed > 1:
            tbt_reward, status = evaluate(self.tbt, self.traj)
        else:
            tbt_reward, status = 0, 0
        print("TBT rob: {}, BT outer logic status: {}".format(tbt_reward, status))
        return obs, tbt_reward, terminated, truncated, info


def make_eval_env(renderer, video=True):
    env = gym.make('PandaPickAndPlaceDense-v3',
                    render_mode="rgb_array",
                    renderer=renderer
                    )
    if video:
        print("Recording episodes ...\n")
        env = gym.wrappers.RecordVideo(
            env,
            video_folder=str(here / "videos"),
            # This will ensure all episodes are recorded as videos.
            episode_trigger=lambda idx: True,
        )
    env = STLMonitorWrapper(env)
    return env

def postprocess_video():
    '''
    Function to slow down the original episode video recording.
    '''
    videos_dir = here / "videos"
    video_files = list(videos_dir.glob("*.mp4"))
    for video_file in video_files:
        fname = str(here / "videos" / video_file.name)
        clip = VideoFileClip(fname)
        final = clip.fx(vfx.speedx, 0.2)
        final.write_videofile(str(here / "videos" / f"{video_file.name}_slowmo.mp4"))

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Run trial episodes on trained TQC pick-and-place model.")
    parser.add_argument(
                        "--renderer",
                        type=str,
                        default="Tiny",
                        help=
                        "Options: 'Tiny' or 'OpenGL'. Use 'OpenGL' when using NVIDIA graphic cards.")
    parser.add_argument(
                        "--n-rollouts",
                        type=int,
                        default=10,
                        help="Number of episodes to run (an integer). Default: 10")
    parser.add_argument(
                        "--no-video",
                        action="store_true",
                        help="Skip video recording and the slow-motion pass.")
    args = parser.parse_args()

    env = make_eval_env(renderer=args.renderer, video=not args.no_video)

    model = TQC.load(
        str(here / "tqc_pandp"),  # trained TQC model
        env=env,
        custom_objects={
            'observation_space': env.observation_space,
            'action_space': env.action_space
        })

    n_rollouts = args.n_rollouts

    n_successes = 0
    for rollout in range(n_rollouts):
        print("\n\nEpisode #", rollout)
        obs, _ = env.reset()
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, r, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            success = info['is_success']
            # env.render()
            n_successes += success

    print("Success Rate: {}".format(n_successes / n_rollouts))

    env.close()

    if not args.no_video:
        postprocess_video()
