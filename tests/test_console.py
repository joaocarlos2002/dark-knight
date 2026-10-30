import io

from qa_workbench.core.console import ensure_utf8_output


def _stream(encoding: str) -> tuple[io.TextIOWrapper, io.BytesIO]:
    raw = io.BytesIO()
    return io.TextIOWrapper(raw, encoding=encoding, write_through=True), raw


def test_a_legacy_code_page_stream_can_print_status_symbols() -> None:
    stream, raw = _stream("cp1252")

    ensure_utf8_output((stream,))
    stream.write("✓ PASSED ◷ PENDING")

    assert raw.getvalue().decode("utf-8") == "✓ PASSED ◷ PENDING"


def test_a_utf8_stream_is_left_alone() -> None:
    stream, raw = _stream("utf-8")

    ensure_utf8_output((stream,))
    stream.write("✓")

    assert raw.getvalue() == "✓".encode()
    assert stream.errors == "strict"


def test_streams_that_cannot_be_reconfigured_are_skipped() -> None:
    class Plain:
        encoding = "cp1252"

    ensure_utf8_output((Plain(),))  # type: ignore[arg-type]


def test_the_default_streams_are_handled() -> None:
    ensure_utf8_output()
