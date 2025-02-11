from __future__ import annotations


class AuditwheelException(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)

    @property
    def message(self) -> str:
        assert isinstance(self.args[0], str)
        return self.args[0]


class InvalidLibc(AuditwheelException):
    pass


class WheelToolsError(AuditwheelException):
    pass


class NonPlatformWheel(AuditwheelException):
    """No ELF binaries in the wheel"""

    def __init__(self, architecture: str | None, libraries: list[str] | None) -> None:
        if architecture is None or not libraries:
            msg = (
                "This does not look like a platform wheel, no ELF executable "
                "or shared library file (including compiled Python C extension) "
                "found in the wheel archive"
            )
        else:
            libraries_str = "\n\t".join(libraries)
            msg = (
                "Invalid binary wheel: no ELF executable or shared library file "
                "(including compiled Python C extension) with a "
                f"{architecture!r} architecure found. The following "
                f"ELF files were found:\n\t{libraries_str}\n"
            )
        super().__init__(msg)
