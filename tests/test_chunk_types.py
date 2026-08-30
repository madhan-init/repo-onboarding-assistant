import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingester.chunk import ALLOW_EXTENSIONS, get_chunk_type


def test_rst_is_indexed():
    """flask writes its entire 104-file manual in .rst. Excluding it means the
    tool cannot answer any question whose real answer is prose -- e.g. file
    uploads, which is documented in docs/patterns/fileuploads.rst and has no
    equivalent in the source."""
    assert ".rst" in ALLOW_EXTENSIONS


def test_rst_classified_as_doc_not_code():
    assert get_chunk_type(".rst") == "doc"


def test_markdown_still_doc():
    assert get_chunk_type(".md") == "doc"


def test_python_still_code():
    assert get_chunk_type(".py") == "code"


def test_config_formats_unchanged():
    for ext in (".json", ".yaml", ".toml"):
        assert get_chunk_type(ext) == "config"
