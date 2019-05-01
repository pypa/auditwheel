import argparse
import pytest
from auditwheel.tools import  EnvironmentDefault


@pytest.mark.parametrize(
    ('environ', 'passed', 'expected'),
    [
        (None, None, 'manylinux1'),
        (None, 'manylinux2010', 'manylinux2010'),
        ('manylinux2010', None, 'manylinux2010'),
        ('manylinux2010', 'linux', 'linux'),
    ],
)
def test_environment_action(monkeypatch, environ, passed, expected):
    choices = ['linux', 'manylinux1', 'manylinux2010']
    argv = []
    if passed:
        argv = ['--plat', passed]
    if environ:
        monkeypatch.setenv('AUDITWHEEL_PLAT', environ)
    p = argparse.ArgumentParser()
    p.add_argument(
        '--plat',
        action=EnvironmentDefault,
        env='AUDITWHEEL_PLAT',
        dest='PLAT',
        choices=choices,
        default='manylinux1')
    args = p.parse_args(argv)
    assert args.PLAT == expected


def test_environment_action_invalid_env(monkeypatch):
    choices = ['linux', 'manylinux1', 'manylinux2010']
    monkeypatch.setenv('AUDITWHEEL_PLAT', 'foo')
    with pytest.raises(argparse.ArgumentError):
        p = argparse.ArgumentParser()
        p.add_argument(
            '--plat',
            action=EnvironmentDefault,
            env='AUDITWHEEL_PLAT',
            dest='PLAT',
            choices=choices,
            default='manylinux1')
