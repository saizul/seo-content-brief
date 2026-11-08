from pathlib import Path

import pytest

from seo_brief.extract import parse_html

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def page_a():
    return parse_html(read_fixture("guide_a.html"), "https://www.example-a.test/post/")


@pytest.fixture(scope="session")
def page_b():
    return parse_html(read_fixture("guide_b.html"), "https://example-b.test/post")


@pytest.fixture(scope="session")
def page_c():
    return parse_html(read_fixture("guide_c.html"), "https://example-c.test/post/")


@pytest.fixture(scope="session")
def page_bn():
    return parse_html(read_fixture("bangla_page.html"), "https://example-bn.test/post/")


@pytest.fixture(scope="session")
def english_pages(page_a, page_b, page_c):
    return [page_a, page_b, page_c]
