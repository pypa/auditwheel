from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from jsonschema import validate

from auditwheel.error import NonPlatformWheelError
from auditwheel.main_show import execute

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "src" / "auditwheel" / "show-schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text())


def _validate_json(output: dict[str, Any]) -> None:
    """Validate JSON output against the show schema."""
    validate(instance=output, schema=_SCHEMA)


class _FakePolicy:
    """Minimal policy stub that supports ordering (needed by _output_json)."""

    def __init__(self, name: str, priority: int) -> None:
        self.name = name
        self.priority = priority

    def __lt__(self, other: Any) -> bool:
        return self.priority < other.priority

    def __gt__(self, other: Any) -> bool:
        return self.priority > other.priority

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _FakePolicy):
            return NotImplemented
        return self.priority == other.priority

    def __hash__(self) -> int:
        return hash(self.priority)


LINUX = _FakePolicy("linux", 0)
MANYLINUX_2_17 = _FakePolicy("manylinux_2_17_x86_64", 50)
MANYLINUX_2_28 = _FakePolicy("manylinux_2_28_x86_64", 70)

ALL_POLICIES = [LINUX, MANYLINUX_2_17, MANYLINUX_2_28]


class _FakePolicies:
    linux = LINUX
    lowest = LINUX
    highest = MANYLINUX_2_28

    def __iter__(self) -> Iterator[_FakePolicy]:
        return iter(ALL_POLICIES)


def _make_winfo(
    *,
    overall_policy: _FakePolicy = MANYLINUX_2_17,
    pyfpe_linux: bool = False,
    ucs_linux: bool = False,
    machine_linux: bool = False,
    versioned_symbols: dict[str, set[str]] | None = None,
    external_libs: dict[str, Path | None] | None = None,
    policy_upgrades_libs: dict[str, Path | None] | None = None,
    policy_upgrades_blacklist: dict[str, list[str]] | None = None,
) -> argparse.Namespace:
    policies = _FakePolicies()

    external_refs = {
        LINUX.name: SimpleNamespace(
            libs=external_libs or {},
            blacklist={},
        ),
        MANYLINUX_2_17.name: SimpleNamespace(libs={}, blacklist={}),
        MANYLINUX_2_28.name: SimpleNamespace(
            libs=policy_upgrades_libs or {},
            blacklist=policy_upgrades_blacklist or {},
        ),
    }

    return argparse.Namespace(
        policies=policies,
        overall_policy=overall_policy,
        pyfpe_policy=LINUX if pyfpe_linux else MANYLINUX_2_17,
        ucs_policy=LINUX if ucs_linux else MANYLINUX_2_17,
        machine_policy=LINUX if machine_linux else MANYLINUX_2_17,
        sym_policy=overall_policy,
        versioned_symbols=versioned_symbols or {},
        external_refs=external_refs,
    )


@pytest.fixture
def patch_wheel_abi(monkeypatch):
    """Patch wheeltools helpers so execute() never touches real wheels.

    Returns a callable that sets the analyze_wheel_abi return value (or
    side_effect) after the fixture is installed.
    """
    monkeypatch.setattr(
        "auditwheel.wheeltools.get_wheel_architecture",
        lambda _fn: None,
    )
    monkeypatch.setattr(
        "auditwheel.wheeltools.get_wheel_libc",
        lambda _fn: None,
    )

    state: dict[str, Any] = {}

    def _set(*, return_value=None, side_effect=None):
        state["return_value"] = return_value
        state["side_effect"] = side_effect

    def _analyze(*_args, **_kwargs):
        if state.get("side_effect") is not None:
            raise state["side_effect"]
        return state["return_value"]

    monkeypatch.setattr("auditwheel.wheel_abi.analyze_wheel_abi", _analyze)
    return _set


def _make_args(
    wheel_path: Path,
    *,
    use_json: bool = True,
    allow_pure_python: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        WHEEL_FILE=wheel_path,
        DISABLE_ISA_EXT_CHECK=False,
        ALLOW_PURE_PY_WHEEL=allow_pure_python,
        JSON=use_json,
        verbose=0,
    )


def test_basic_json_output(tmp_path, capsys, patch_wheel_abi):
    wheel = tmp_path / "foo-1.0-cp39-cp39-linux_x86_64.whl"
    wheel.write_text("")
    patch_wheel_abi(return_value=_make_winfo())

    retval = execute(_make_args(wheel), argparse.ArgumentParser())

    assert retval == 0
    output = json.loads(capsys.readouterr().out)
    _validate_json(output)
    assert output["version"] == 1
    assert output["wheel"] == wheel.name
    assert output["pure"] is False
    assert output["overall_tag"] == "manylinux_2_17_x86_64"
    assert output["sym_tag"] == "manylinux_2_17_x86_64"
    assert output["pyfpe"] is False
    assert output["ucs2"] is False
    assert output["unsupported_isa"] is False
    assert output["versioned_symbols"] == {}
    assert output["external_libs"] == {}
    assert output["policy_upgrades"] == {}


def test_json_with_versioned_symbols(tmp_path, capsys, patch_wheel_abi):
    wheel = tmp_path / "foo-1.0-cp39-cp39-linux_x86_64.whl"
    wheel.write_text("")
    patch_wheel_abi(
        return_value=_make_winfo(
            versioned_symbols={"libm.so.6": {"GLIBC_2.17", "GLIBC_2.5"}},
        ),
    )

    retval = execute(_make_args(wheel), argparse.ArgumentParser())

    assert retval == 0
    output = json.loads(capsys.readouterr().out)
    _validate_json(output)
    assert output["versioned_symbols"] == {
        "libm.so.6": ["GLIBC_2.17", "GLIBC_2.5"],
    }


def test_json_with_external_libs(tmp_path, capsys, patch_wheel_abi):
    wheel = tmp_path / "foo-1.0-cp39-cp39-linux_x86_64.whl"
    wheel.write_text("")
    patch_wheel_abi(
        return_value=_make_winfo(
            external_libs={
                "libfoo.so": Path("/usr/lib/libfoo.so"),
                "libbar.so": None,
            },
        ),
    )

    retval = execute(_make_args(wheel), argparse.ArgumentParser())

    assert retval == 0
    output = json.loads(capsys.readouterr().out)
    _validate_json(output)
    assert output["external_libs"] == {
        "libbar.so": None,
        "libfoo.so": "/usr/lib/libfoo.so",
    }


def test_json_with_policy_upgrades(tmp_path, capsys, patch_wheel_abi):
    wheel = tmp_path / "foo-1.0-cp39-cp39-linux_x86_64.whl"
    wheel.write_text("")
    patch_wheel_abi(
        return_value=_make_winfo(
            policy_upgrades_libs={"libextra.so": Path("/usr/lib/libextra.so")},
            policy_upgrades_blacklist={"libsym.so": ["bad_sym"]},
        ),
    )

    retval = execute(_make_args(wheel), argparse.ArgumentParser())

    assert retval == 0
    output = json.loads(capsys.readouterr().out)
    _validate_json(output)
    assert "manylinux_2_28_x86_64" in output["policy_upgrades"]
    upgrade = output["policy_upgrades"]["manylinux_2_28_x86_64"]
    assert upgrade["libs_to_eliminate"] == ["libextra.so"]
    assert upgrade["blacklisted_symbols"] == {"libsym.so": ["bad_sym"]}


@pytest.mark.parametrize(
    ("flag_kwarg", "output_key"),
    [
        ("pyfpe_linux", "pyfpe"),
        ("ucs_linux", "ucs2"),
        ("machine_linux", "unsupported_isa"),
    ],
    ids=["pyfpe", "ucs2", "unsupported_isa"],
)
def test_json_boolean_flags(tmp_path, capsys, patch_wheel_abi, flag_kwarg, output_key):
    wheel = tmp_path / "foo-1.0-cp39-cp39-linux_x86_64.whl"
    wheel.write_text("")
    patch_wheel_abi(
        return_value=_make_winfo(
            pyfpe_linux=flag_kwarg == "pyfpe_linux",
            ucs_linux=flag_kwarg == "ucs_linux",
            machine_linux=flag_kwarg == "machine_linux",
        ),
    )

    retval = execute(_make_args(wheel), argparse.ArgumentParser())

    assert retval == 0
    output = json.loads(capsys.readouterr().out)
    _validate_json(output)
    assert output[output_key] is True


def test_no_json_flag_uses_text_output(tmp_path, capsys, patch_wheel_abi):
    wheel = tmp_path / "foo-1.0-cp39-cp39-linux_x86_64.whl"
    wheel.write_text("")
    patch_wheel_abi(return_value=_make_winfo())

    retval = execute(_make_args(wheel, use_json=False), argparse.ArgumentParser())

    assert retval == 0
    out = capsys.readouterr().out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert "consistent with the following" in out
    assert "platform tag" in out


def test_json_with_sym_policy_constraint(tmp_path, capsys, patch_wheel_abi):
    wheel = tmp_path / "foo-1.0-cp39-cp39-linux_x86_64.whl"
    wheel.write_text("")
    winfo = _make_winfo()
    winfo.sym_policy = LINUX
    patch_wheel_abi(return_value=winfo)

    retval = execute(_make_args(wheel), argparse.ArgumentParser())

    assert retval == 0
    output = json.loads(capsys.readouterr().out)
    _validate_json(output)
    assert output["sym_tag"] == "linux"
    assert output["overall_tag"] == "manylinux_2_17_x86_64"


def _setup_pure_wheel(tmp_path, monkeypatch):
    """Set up a pure Python wheel that raises NonPlatformWheelError."""
    wheel = tmp_path / "foo-1.0-py3-none-any.whl"
    wheel.write_text("")

    error = NonPlatformWheelError(None, None)

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(
        "auditwheel.wheeltools.get_wheel_architecture",
        _raise,
    )
    monkeypatch.setattr(
        "auditwheel.wheeltools.get_wheel_libc",
        lambda _fn: None,
    )
    monkeypatch.setattr(
        "auditwheel.wheel_abi.analyze_wheel_abi",
        _raise,
    )
    return wheel


def test_json_on_non_platform_wheel_error(tmp_path, capsys, monkeypatch):
    wheel = _setup_pure_wheel(tmp_path, monkeypatch)

    retval = execute(_make_args(wheel), argparse.ArgumentParser())

    assert retval == 1
    output = json.loads(capsys.readouterr().out)
    _validate_json(output)
    assert output["version"] == 1
    assert output["wheel"] == wheel.name
    assert "error" in output
    assert "platform wheel" in output["error"]


def test_json_on_pure_wheel_allowed(tmp_path, capsys, monkeypatch):
    wheel = _setup_pure_wheel(tmp_path, monkeypatch)

    retval = execute(
        _make_args(wheel, allow_pure_python=True),
        argparse.ArgumentParser(),
    )

    assert retval == 0
    output = json.loads(capsys.readouterr().out)
    _validate_json(output)
    assert output["version"] == 1
    assert output["wheel"] == wheel.name
    assert output["pure"] is True
    assert "error" not in output


def test_nonexistent_wheel_with_json(tmp_path):
    wheel = tmp_path / "nonexistent.whl"

    with pytest.raises(SystemExit):
        execute(_make_args(wheel), argparse.ArgumentParser())
