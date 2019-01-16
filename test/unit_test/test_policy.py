import unittest
from src.rl.policy.policy import Policy
from gym.core import Space
from gym.spaces.discrete import Discrete
from src.envs.env_spec import EnvSpec


class TestPolicy(unittest.TestCase):
    def test_init(self):
        # a = Policy(action_space=Space(), obs_space=Space())
        a = Policy(EnvSpec(action_space=Discrete(10), obs_space=Discrete(10)))


if __name__ == '__main__':
    unittest.main()
