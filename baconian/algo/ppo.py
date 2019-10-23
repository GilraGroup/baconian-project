from baconian.core.core import EnvSpec
from baconian.algo.rl_algo import ModelFreeAlgo, OnPolicyAlgo
from baconian.config.dict_config import DictConfig
from typeguard import typechecked
import tensorflow as tf
import numpy as np
from baconian.common.sampler.sample_data import TrajectoryData, TransitionData, SampleData
from baconian.tf.tf_parameters import ParametersWithTensorflowVariable
from baconian.config.global_config import GlobalConfig
from baconian.algo.policy.policy import StochasticPolicy
from baconian.algo.value_func import VValueFunction
from baconian.tf.util import *
from baconian.common.misc import *
from baconian.algo.misc import SampleProcessor
from baconian.common.logging import record_return_decorator
from baconian.core.status import register_counter_info_to_status_decorator
from baconian.algo.misc.placeholder_input import MultiPlaceholderInput, PlaceholderInput
from baconian.common.error import *
from baconian.common.data_pre_processing import RunningStandardScaler
from baconian.common.special import *


class PPO(ModelFreeAlgo, OnPolicyAlgo, MultiPlaceholderInput):
    required_key_dict = DictConfig.load_json(file_path=GlobalConfig().DEFAULT_PPO_REQUIRED_KEY_LIST)

    @typechecked
    def __init__(self, env_spec: EnvSpec,
                 stochastic_policy: StochasticPolicy,
                 config_or_config_dict: (DictConfig, dict),
                 value_func: VValueFunction,
                 name='ppo'):
        ModelFreeAlgo.__init__(self, env_spec=env_spec, name=name)

        self.config = construct_dict_config(config_or_config_dict, self)
        self.policy = stochastic_policy
        self.value_func = value_func
        to_ph_parameter_dict = dict()
        self.trajectory_memory = TrajectoryData(env_spec=env_spec)
        self.transition_data_for_trajectory = TransitionData(env_spec=env_spec)
        self.value_func_train_data_buffer = None
        # self.scaler = Scaler(obs_dim=self.env_spec.flat_obs_dim)
        self.scaler = RunningStandardScaler(dims=self.env_spec.flat_obs_dim)

        with tf.variable_scope(name):
            self.advantages_ph = tf.placeholder(tf.float32, (None,), 'advantages')
            self.v_func_val_ph = tf.placeholder(tf.float32, (None,), 'val_valfunc')
            dist_info_list = self.policy.get_dist_info()
            self.old_dist_tensor = [
                (tf.placeholder(**dict(dtype=dist_info['dtype'],
                                       shape=dist_info['shape'],
                                       name=dist_info['name'])), dist_info['name']) for dist_info in
                dist_info_list
            ]
            self.old_policy = self.policy.make_copy(reuse=False,
                                                    name_scope='old_{}'.format(self.policy.name),
                                                    name='old_{}'.format(self.policy.name),
                                                    distribution_tensors_tuple=tuple(self.old_dist_tensor))
            to_ph_parameter_dict['beta'] = tf.placeholder(tf.float32, (), 'beta')
            to_ph_parameter_dict['eta'] = tf.placeholder(tf.float32, (), 'eta')
            to_ph_parameter_dict['kl_target'] = tf.placeholder(tf.float32, (), 'kl_target')
            to_ph_parameter_dict['lr_multiplier'] = tf.placeholder(tf.float32, (), 'lr_multiplier')

        self.parameters = ParametersWithTensorflowVariable(tf_var_list=[],
                                                           rest_parameters=dict(
                                                               advantages_ph=self.advantages_ph,
                                                               v_func_val_ph=self.v_func_val_ph,
                                                           ),
                                                           to_ph_parameter_dict=to_ph_parameter_dict,
                                                           name='ppo_param',
                                                           save_rest_param_flag=False,
                                                           source_config=self.config,
                                                           require_snapshot=False)
        with tf.variable_scope(name):
            with tf.variable_scope('train'):
                self.kl = tf.reduce_mean(self.old_policy.kl(other=self.policy))
                self.average_entropy = tf.reduce_mean(self.policy.entropy())
                self.policy_loss, self.policy_optimizer, self.policy_update_op = self._setup_policy_loss()
                self.value_func_loss, self.value_func_optimizer, self.value_func_update_op = self._setup_value_func_loss()
        var_list = get_tf_collection_var_list(
            '{}/train'.format(name)) + self.policy_optimizer.variables() + self.value_func_optimizer.variables()
        self.parameters.set_tf_var_list(tf_var_list=sorted(list(set(var_list)), key=lambda x: x.name))

        MultiPlaceholderInput.__init__(self,
                                       sub_placeholder_input_list=[dict(obj=self.value_func,
                                                                        attr_name='value_func',
                                                                        ),
                                                                   dict(obj=self.policy,
                                                                        attr_name='policy')],
                                       parameters=self.parameters)

    @register_counter_info_to_status_decorator(increment=1, info_key='init', under_status='JUST_INITED')
    def init(self, sess=None, source_obj=None):
        self.policy.init()
        self.value_func.init()
        self.parameters.init()
        if source_obj:
            self.copy_from(source_obj)
        super().init()

    @record_return_decorator(which_recorder='self')
    @register_counter_info_to_status_decorator(increment=1, info_key='train', under_status='TRAIN')
    def train(self, trajectory_data: TrajectoryData = None, train_iter=None, sess=None) -> dict:
        super(PPO, self).train()
        if trajectory_data is None:
            trajectory_data = self.trajectory_memory
        if len(trajectory_data) == 0:
            raise MemoryBufferLessThanBatchSizeError('not enough trajectory data')
        tf_sess = sess if sess else tf.get_default_session()
        SampleProcessor.add_estimated_v_value(trajectory_data, value_func=self.value_func)
        SampleProcessor.add_discount_sum_reward(trajectory_data,
                                                gamma=self.parameters('gamma'))
        SampleProcessor.add_gae(trajectory_data,
                                gamma=self.parameters('gamma'),
                                name='advantage_set',
                                lam=self.parameters('lam'),
                                value_func=self.value_func)

        train_data = trajectory_data.return_as_transition_data(shuffle_flag=False)
        SampleProcessor.normalization(train_data, key='advantage_set')
        policy_res_dict = self._update_policy(train_data=train_data,
                                              train_iter=train_iter if train_iter else self.parameters(
                                                  'policy_train_iter'),
                                              sess=tf_sess)
        value_func_res_dict = self._update_value_func(train_data=train_data,
                                                      train_iter=train_iter if train_iter else self.parameters(
                                                          'value_func_train_iter'),
                                                      sess=tf_sess)
        self.trajectory_memory.reset()
        return {
            **policy_res_dict,
            **value_func_res_dict
        }

    @register_counter_info_to_status_decorator(increment=1, info_key='test', under_status='TEST')
    def test(self, *arg, **kwargs) -> dict:
        return super().test(*arg, **kwargs)

    @register_counter_info_to_status_decorator(increment=1, info_key='predict')
    def predict(self, obs: np.ndarray, sess=None, batch_flag: bool = False):
        tf_sess = sess if sess else tf.get_default_session()
        obs = make_batch(obs, original_shape=self.env_spec.obs_shape)
        obs = self.scaler.process(data=obs)
        ac = self.policy.forward(obs=obs, sess=tf_sess, feed_dict=self.parameters.return_tf_parameter_feed_dict())
        return ac

    def append_to_memory(self, samples: SampleData):
        # todo how to make sure the data's time sequential
        iter_samples = samples.return_generator()
        # scale, offset = self.scaler.get()
        obs_list = []
        for state, new_state, action, reward, done in iter_samples:
            obs_list.append(state)
            self.transition_data_for_trajectory.append(state=self.scaler.process(state),
                                                       new_state=self.scaler.process(new_state),
                                                       action=action,
                                                       reward=reward,
                                                       done=done)
            if done is True:
                self.trajectory_memory.append(self.transition_data_for_trajectory)
                self.transition_data_for_trajectory.reset()
        self.scaler.update_scaler(data=np.array(obs_list))

    @record_return_decorator(which_recorder='self')
    def save(self, global_step, save_path=None, name=None, **kwargs):
        save_path = save_path if save_path else GlobalConfig().DEFAULT_MODEL_CHECKPOINT_PATH
        name = name if name else self.name
        MultiPlaceholderInput.save(self, save_path=save_path, global_step=global_step, name=name, **kwargs)
        return dict(check_point_save_path=save_path, check_point_save_global_step=global_step,
                    check_point_save_name=name)

    @record_return_decorator(which_recorder='self')
    def load(self, path_to_model, model_name, global_step=None, **kwargs):
        MultiPlaceholderInput.load(self, path_to_model, model_name, global_step, **kwargs)
        return dict(check_point_load_path=path_to_model, check_point_load_global_step=global_step,
                    check_point_load_name=model_name)

    def _setup_policy_loss(self):
        """
        Code clip from pat-cody
        Three loss terms:
            1) standard policy gradient
            2) D_KL(pi_old || pi_new)
            3) Hinge loss on [D_KL - kl_targ]^2

        See: https://arxiv.org/pdf/1707.02286.pdf
        """

        if self.parameters('clipping_range') is not None:
            pg_ratio = tf.exp(self.policy.log_prob() - self.old_policy.log_prob())
            clipped_pg_ratio = tf.clip_by_value(pg_ratio, 1 - self.parameters('clipping_range')[0],
                                                1 + self.parameters('clipping_range')[1])
            surrogate_loss = tf.minimum(self.advantages_ph * pg_ratio,
                                        self.advantages_ph * clipped_pg_ratio)
            loss = -tf.reduce_mean(surrogate_loss)
        else:
            loss1 = -tf.reduce_mean(self.advantages_ph *
                                    tf.exp(self.policy.log_prob() - self.old_policy.log_prob()))
            loss2 = tf.reduce_mean(self.parameters('beta') * self.kl)
            loss3 = self.parameters('eta') * tf.square(
                tf.maximum(0.0, self.kl - 2.0 * self.parameters('kl_target')))
            loss = loss1 + loss2 + loss3
            self.loss1 = loss1
            self.loss2 = loss2
            self.loss3 = loss3
        if isinstance(self.policy, PlaceholderInput):
            reg_list = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES, scope=self.policy.name_scope)
            if len(reg_list) > 0:
                reg_loss = tf.reduce_sum(reg_list)
                loss += reg_loss

        optimizer = tf.train.AdamOptimizer(
            learning_rate=self.parameters('policy_lr') * self.parameters('lr_multiplier'))
        train_op = optimizer.minimize(loss, var_list=self.policy.parameters('tf_var_list'))
        return loss, optimizer, train_op

    def _setup_value_func_loss(self):
        # todo update the value_func design
        loss = tf.reduce_mean(tf.square(self.value_func.v_tensor - self.v_func_val_ph))
        reg_loss = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES, scope=self.value_func.name_scope)
        if len(reg_loss) > 0:
            loss += tf.reduce_sum(reg_loss)

        optimizer = tf.train.AdamOptimizer(self.parameters('value_func_lr'))
        train_op = optimizer.minimize(loss, var_list=self.value_func.parameters('tf_var_list'))
        return loss, optimizer, train_op

    def _update_policy(self, train_data: TransitionData, train_iter, sess):
        old_policy_feed_dict = dict()

        res = sess.run([getattr(self.policy, tensor[1]) for tensor in self.old_dist_tensor],
                       feed_dict={
                           self.policy.parameters('state_input'): train_data('state_set'),
                           self.policy.parameters('action_input'): train_data('action_set'),
                           **self.parameters.return_tf_parameter_feed_dict()
                       })

        for tensor, val in zip(self.old_dist_tensor, res):
            old_policy_feed_dict[tensor[0]] = val

        feed_dict = {
            self.policy.parameters('action_input'): train_data('action_set'),
            self.old_policy.parameters('action_input'): train_data('action_set'),
            self.policy.parameters('state_input'): train_data('state_set'),
            self.advantages_ph: train_data('advantage_set'),
            **self.parameters.return_tf_parameter_feed_dict(),
            **old_policy_feed_dict
        }
        average_loss, average_kl, average_entropy = 0.0, 0.0, 0.0
        total_epoch = 0
        kl = None
        for i in range(train_iter):
            loss, kl, entropy, _ = sess.run(
                [self.policy_loss, self.kl, self.average_entropy, self.policy_update_op],
                feed_dict=feed_dict)
            average_loss += loss
            average_kl += kl
            average_entropy += entropy
            total_epoch = i + 1
            if kl > self.parameters('kl_target', require_true_value=True) * 4:
                # early stopping if D_KL diverges badly
                break
        average_loss, average_kl, average_entropy = average_loss / total_epoch, average_kl / total_epoch, average_entropy / total_epoch

        if kl > self.parameters('kl_target', require_true_value=True) * 2:  # servo beta to reach D_KL target
            self.parameters.set(key='beta',
                                new_val=np.minimum(35, 1.5 * self.parameters('beta', require_true_value=True)))
            if self.parameters('beta', require_true_value=True) > 30 and self.parameters('lr_multiplier',
                                                                                         require_true_value=True) > 0.1:
                self.parameters.set(key='lr_multiplier',
                                    new_val=self.parameters('lr_multiplier', require_true_value=True) / 1.5)
        elif kl < self.parameters('kl_target', require_true_value=True) / 2:
            self.parameters.set(key='beta',
                                new_val=np.maximum(1 / 35, self.parameters('beta', require_true_value=True) / 1.5))

            if self.parameters('beta', require_true_value=True) < (1 / 30) and self.parameters('lr_multiplier',
                                                                                               require_true_value=True) < 10:
                self.parameters.set(key='lr_multiplier',
                                    new_val=self.parameters('lr_multiplier', require_true_value=True) * 1.5)
        return dict(
            policy_average_loss=average_loss,
            policy_average_kl=average_kl,
            policy_average_entropy=average_entropy,
            policy_total_train_epoch=total_epoch
        )

    def _update_value_func(self, train_data: TransitionData, train_iter, sess):
        if self.value_func_train_data_buffer is None:
            self.value_func_train_data_buffer = train_data
        else:
            self.value_func_train_data_buffer.union(train_data)
        y_hat = self.value_func.forward(obs=train_data('state_set'))
        old_exp_var = 1 - np.var(self.value_func_train_data_buffer('discount_set') - y_hat) / np.var(
            self.value_func_train_data_buffer('discount_set'))
        for i in range(train_iter):
            data_gen = self.value_func_train_data_buffer.return_generator(
                batch_size=self.parameters('value_func_train_batch_size'),
                infinite_run=False,
                shuffle_flag=True,
                assigned_keys=('state_set', 'new_state_set', 'action_set', 'reward_set', 'done_set', 'discount_set'))
            for batch in data_gen:
                loss, _ = sess.run([self.value_func_loss, self.value_func_update_op],
                                   feed_dict={
                                       self.value_func.state_input: batch[0],
                                       self.v_func_val_ph: batch[5],
                                       **self.parameters.return_tf_parameter_feed_dict()
                                   })
        y_hat = self.value_func.forward(obs=self.value_func_train_data_buffer('state_set'))
        loss = np.mean(np.square(y_hat - self.value_func_train_data_buffer('discount_set')))
        exp_var = 1 - np.var(self.value_func_train_data_buffer('discount_set') - y_hat) / np.var(
            self.value_func_train_data_buffer('discount_set'))
        return dict(
            value_func_loss=loss,
            value_func_policy_exp_var=exp_var,
            value_func_policy_old_exp_var=old_exp_var
        )
