import unittest
from src.envs.gym_env import make
from src.envs.env_spec import EnvSpec
import tensorflow as tf
from src.tf.util import create_new_tf_session
import numpy as np
from src.rl.policy.normal_distribution_mlp import NormalDistributionMLPPolicy
from src.common.special import *


class TestNormalDistMLPPolicy(unittest.TestCase):
    def test_mlp_norm_dist_policy(self):
        if tf.get_default_session():
            sess = tf.get_default_session()
            sess.__exit__(None, None, None)
        tf.reset_default_graph()
        env = make('Swimmer-v1')
        env.reset()
        env_spec = EnvSpec(obs_space=env.observation_space,
                           action_space=env.action_space)
        sess = create_new_tf_session(cuda_device=0)

        policy = NormalDistributionMLPPolicy(env_spec=env_spec,
                                             name_scope='mlp_policy',
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
                                                     "N_UNITS": env_spec.flat_action_dim,
                                                     "TYPE": "DENSE",
                                                     "W_NORMAL_STDDEV": 0.03
                                                 }
                                             ],
                                             output_high=None,
                                             output_low=None,
                                             output_norm=None,
                                             input_norm=None,
                                             reuse=False)
        self.assertIsNotNone(tf.get_default_session())
        policy.init()
        dist_info = policy.get_dist_info()
        self.assertTrue(np.equal(dist_info[0]['shape'], policy.mean_output.shape.as_list()).all())
        self.assertTrue(np.equal(dist_info[1]['shape'], policy.logvar_output.shape.as_list()).all())
        for _ in range(10):
            ac = policy.forward(obs=env.observation_space.sample())
            self.assertTrue(env.action_space.contains(ac[0]))
        p2 = policy.make_copy(name_scope='test',
                              reuse=False)
        p2.init()
        self.assertGreater(len(policy.parameters('tf_var_list')), 0)
        self.assertGreater(len(p2.parameters('tf_var_list')), 0)
        for var1, var2 in zip(policy.parameters('tf_var_list'), p2.parameters('tf_var_list')):
            self.assertEqual(var1.shape, var2.shape)
            self.assertNotEqual(id(var1), id(var2))

        p3 = policy.make_copy(name_scope='mlp_policy',
                              reuse=True)
        p3.init()
        self.assertGreater(len(p3.parameters('tf_var_list')), 0)
        for var1, var2 in zip(policy.parameters('tf_var_list'), p3.parameters('tf_var_list')):
            self.assertEqual(var1.shape, var2.shape)
            self.assertEqual(id(var1), id(var2))

        policy.copy(p2)
        res = []
        res2 = []
        for var1, var2, var3 in zip(policy.parameters('tf_var_list'), p2.parameters('tf_var_list'),
                                    p3.parameters('tf_var_list')):
            re1, re2, re3 = sess.run([var1, var2, var3])
            res.append(np.isclose(re1, re2).all())
            self.assertTrue(np.isclose(re1, re3).all())
            res2.append(np.isclose(re3, re2).all())
        self.assertFalse(np.array(res).all())
        self.assertFalse(np.array(res2).all())

    def test_func(self):
        if tf.get_default_session():
            sess = tf.get_default_session()
            sess.__exit__(None, None, None)
        tf.reset_default_graph()
        env = make('Swimmer-v1')
        env.reset()
        env_spec = EnvSpec(obs_space=env.observation_space,
                           action_space=env.action_space)
        sess = create_new_tf_session(cuda_device=0)

        policy = NormalDistributionMLPPolicy(env_spec=env_spec,
                                             name_scope='mlp_policy',
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
                                                     "N_UNITS": env_spec.flat_action_dim,
                                                     "TYPE": "DENSE",
                                                     "W_NORMAL_STDDEV": 0.03
                                                 }
                                             ],
                                             output_high=None,
                                             output_low=None,
                                             output_norm=None,
                                             input_norm=None,
                                             reuse=False)
        self.assertIsNotNone(tf.get_default_session())
        policy.init()
        print(
            policy.compute_dist_info(name='entropy',
                                     feed_dict={
                                         policy.state_input: make_batch(env_spec.obs_space.sample(),
                                                                        original_shape=env_spec.obs_shape)}))
        print(
            policy.compute_dist_info(name='prob',
                                     value=env_spec.action_space.sample(),
                                     feed_dict={
                                         policy.state_input: make_batch(env_spec.obs_space.sample(),
                                                                        original_shape=env_spec.obs_shape)}))
        new_policy = policy.make_copy(
            reuse=False,
            name_scope='new_p'
        )
        new_policy.init()
        for var1, var2 in zip(policy.parameters('tf_var_list'), new_policy.parameters('tf_var_list')):
            print(var1.name)
            print(var2.name)
            self.assertNotEqual(var1.name, var2.name)
            self.assertNotEqual(id(var1), id(var2))
        obs1 = make_batch(env_spec.obs_space.sample(),
                          original_shape=env_spec.obs_shape,
                          )
        obs2 = make_batch(env_spec.obs_space.sample(),
                          original_shape=env_spec.obs_shape)
        kl1 = policy.compute_dist_info(name='kl', other=new_policy, feed_dict={
            policy.state_input: obs1,
            new_policy.state_input: obs2
        })
        kl2 = sess.run(policy.kl(other=new_policy), feed_dict={
            policy.state_input: obs1,
            new_policy.state_input: obs2
        })
        self.assertTrue(np.isclose(kl1, kl2).all())


if __name__ == '__main__':
    unittest.main()
