from __future__ import annotations

from auditwheel.policy import WheelPolicies


def test_policy_checks_glibc():
    wheel_policy = WheelPolicies()

    policy = wheel_policy.versioned_symbols_policy({"some_library.so": {"GLIBC_2.17"}})
    assert policy > wheel_policy.lowest
    policy = wheel_policy.versioned_symbols_policy({"some_library.so": {"GLIBC_999"}})
    assert policy == wheel_policy.lowest
    policy = wheel_policy.versioned_symbols_policy(
        {"some_library.so": {"OPENSSL_1_1_0"}}
    )
    assert policy == wheel_policy.highest
    policy = wheel_policy.versioned_symbols_policy({"some_library.so": {"IAMALIBRARY"}})
    assert policy == wheel_policy.highest
