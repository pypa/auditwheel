from jsonschema import validate
from auditwheel.policy import (load_policies, _load_policy_schema,
                               versioned_symbols_policy,
                               Platform, get_policy_platform)


def test_manylinux_policy():
    policies = load_policies(Platform.Manylinux)
    policy_schema = _load_policy_schema()
    validate(policies.policies, policy_schema)


def test_policy_checks_glibc():
    policies = load_policies(get_policy_platform())

    policy = versioned_symbols_policy({"some_library.so": {"GLIBC_2.17"}})
    assert policy > policies.lowest
    policy = versioned_symbols_policy({"some_library.so": {"GLIBC_999"}})
    assert policy == policies.lowest
    policy = versioned_symbols_policy({"some_library.so": {"OPENSSL_1_1_0"}})
    assert policy == policies.highest
    policy = versioned_symbols_policy({"some_library.so": {"IAMALIBRARY"}})
    assert policy == policies.highest
