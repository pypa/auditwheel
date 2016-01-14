from jsonschema import validate
from auditwheel.policy import load_policies, _load_policy_schema


def test_policy():
    policy = load_policies()
    policy_schema = _load_policy_schema()
    validate(policy, policy_schema)

