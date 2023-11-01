from __future__ import annotations

from jsonschema import validate

from auditwheel.policy import (
    WheelPolicies,
    _load_policy_schema,
    versioned_symbols_policy,
)


def test_policy():
    wheel_policy = WheelPolicies()
    policy_schema = _load_policy_schema()
    validate(wheel_policy.policies, policy_schema)


def test_policy_checks_glibc():
    wheel_policy = WheelPolicies()

    policy = versioned_symbols_policy(wheel_policy, {"some_library.so": {"GLIBC_2.17"}})
    assert policy > wheel_policy.priority_lowest
    policy = versioned_symbols_policy(wheel_policy, {"some_library.so": {"GLIBC_999"}})
    assert policy == wheel_policy.priority_lowest
    policy = versioned_symbols_policy(
        wheel_policy, {"some_library.so": {"OPENSSL_1_1_0"}}
    )
    assert policy == wheel_policy.priority_highest
    policy = versioned_symbols_policy(
        wheel_policy, {"some_library.so": {"IAMALIBRARY"}}
    )
    assert policy == wheel_policy.priority_highest
