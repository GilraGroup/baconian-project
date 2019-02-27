from mobrl.envs.gym_env import make
from mobrl.envs.env_spec import EnvSpec
from mobrl.algo.rl.value_func.mlp_q_value import MLPQValueFunction
from mobrl.agent.agent import Agent
from mobrl.algo.rl.misc.exploration_strategy.epsilon_greedy import EpsilonGreedy
from mobrl.core.pipelines.model_based_pipeline import ModelBasedPipeline
from mobrl.algo.rl.model_based.models.mlp_dynamics_model import ContinuousMLPGlobalDynamicsModel
from mobrl.algo.rl.model_based.sample_with_model import SampleWithDynamics
from mobrl.test.tests.test_setup import TestWithAll
from mobrl.algo.rl.model_free.dqn import DQN


class TestModelFreePipeline(TestWithAll):
    def test_agent(self):
        env = make('Acrobot-v1')
        env_spec = EnvSpec(obs_space=env.observation_space,
                           action_space=env.action_space)

        mlp_q = MLPQValueFunction(env_spec=env_spec,
                                  name_scope='mlp_q',
                                  name='mlp_q',
                                  output_low=None,
                                  output_high=None,
                                  mlp_config=[
                                      {
                                          "ACT": "RELU",
                                          "B_INIT_VALUE": 0.0,
                                          "NAME": "1",
                                          "N_UNITS": 16,
                                          "TYPE": "DENSE",
                                          "W_NORMAL_STDDEV": 0.03
                                      },
                                      {
                                          "ACT": "LINEAR",
                                          "B_INIT_VALUE": 0.0,
                                          "NAME": "OUPTUT",
                                          "N_UNITS": 1,
                                          "TYPE": "DENSE",
                                          "W_NORMAL_STDDEV": 0.03
                                      }
                                  ])
        dqn = DQN(env_spec=env_spec,
                  config_or_config_dict=dict(REPLAY_BUFFER_SIZE=1000,
                                             GAMMA=0.99,
                                             BATCH_SIZE=10,
                                             Q_NET_L1_NORM_SCALE=0.001,
                                             Q_NET_L2_NORM_SCALE=0.001,
                                             TRAIN_ITERATION=10,
                                             LEARNING_RATE=0.001,
                                             DECAY=0.5),
                  value_func=mlp_q)

        mlp_dyna = ContinuousMLPGlobalDynamicsModel(
            env_spec=env_spec,
            name_scope='mlp_dyna',
            name='mlp_dyna',
            output_low=env_spec.obs_space.low,
            output_high=env_spec.obs_space.high,
            l1_norm_scale=1.0,
            l2_norm_scale=1.0,
            learning_rate=0.01,
            mlp_config=[
                {
                    "ACT": "RELU",
                    "B_INIT_VALUE": 0.0,
                    "NAME": "1",
                    "N_UNITS": 16,
                    "TYPE": "DENSE",
                    "W_NORMAL_STDDEV": 0.03
                },
                {
                    "ACT": "LINEAR",
                    "B_INIT_VALUE": 0.0,
                    "NAME": "OUPTUT",
                    "N_UNITS": 6,
                    "TYPE": "DENSE",
                    "W_NORMAL_STDDEV": 0.03
                }
            ])

        algo = SampleWithDynamics(env_spec=env_spec, dynamics_model=mlp_dyna,
                                  model_free_algo=dqn,
                                  config_or_config_dict=dict(
                                      dynamics_model_train_iter=10,
                                      model_free_algo_train_iter=10
                                  ))

        agent = Agent(env=env, algo=algo, name='agent',
                      exploration_strategy=EpsilonGreedy(action_space=dqn.env_spec.action_space,
                                                         init_random_prob=0.5,
                                                         decay_type=None),
                      env_spec=env_spec)
        pipeline = ModelBasedPipeline(agent=agent, env=env,
                                      config_or_config_dict=dict(TEST_SAMPLES_COUNT=100,
                                                                 TRAIN_SAMPLES_COUNT=100,
                                                                 TOTAL_SAMPLES_COUNT=1000))
        pipeline.launch()