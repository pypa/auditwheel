from jsonschema import validate
from deloc8.policy import _load_policy, _load_policy_schema


def test_policy():
    policy = _load_policy()
    policy_schema = _load_policy_schema()
    validate(policy, policy_schema)

