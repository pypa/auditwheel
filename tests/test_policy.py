from jsonschema import validate
from auditwheel.policy import (load_policies, _load_policy_schema,
                               versioned_symbols_policy, POLICY_PRIORITY_LOWEST)


def test_policy():
    policy = load_policies()
    policy_schema = _load_policy_schema()
    validate(policy, policy_schema)


def test_policy_checks_glibc():
    policy = versioned_symbols_policy(
        {
            "some_library.so": {
                "GLIBC_2.5",
                "OPENSSL_1.0.1_EC",
                "some_library.so",
            },
        })
    assert policy > POLICY_PRIORITY_LOWEST
    policy = versioned_symbols_policy(
        {
            "some_library.so": {
                "GLIBC_999",
                "OPENSSL_1.0.1_EC",
                "some_library.so",
            },
        })
    assert policy == POLICY_PRIORITY_LOWEST
