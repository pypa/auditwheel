from jsonschema import validate
from auditwheel.policy import (load_policies, _load_policy_schema,
                               versioned_symbols_policy,
                               POLICY_PRIORITY_HIGHEST,
                               POLICY_PRIORITY_LOWEST)


def test_policy():
    policy = load_policies()
    policy_schema = _load_policy_schema()
    validate(policy, policy_schema)


def test_policy_checks_glibc():
    policy = versioned_symbols_policy({"some_library.so": {"GLIBC_2.17"}})
    assert policy > POLICY_PRIORITY_LOWEST
    policy = versioned_symbols_policy({"some_library.so": {"GLIBC_999"}})
    assert policy == POLICY_PRIORITY_LOWEST
    policy = versioned_symbols_policy({"some_library.so": {"OPENSSL_1_1_0"}})
    assert policy == POLICY_PRIORITY_HIGHEST
    policy = versioned_symbols_policy({"some_library.so": {"IAMALIBRARY"}})
    assert policy == POLICY_PRIORITY_HIGHEST
