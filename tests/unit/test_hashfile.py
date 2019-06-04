from io import BytesIO

from auditwheel.hashfile import hashfile


def test_hash():
    # GIVEN
    mock_file = BytesIO(b"this is a test file")

    # WHEN
    result = hashfile(mock_file)

    # THEN
    assert result == "5881707e54b0112f901bc83a1ffbacac8fab74ea46a6f706a3efc5f7d4c1c625"
