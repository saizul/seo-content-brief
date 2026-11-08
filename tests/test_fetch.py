import json

import pytest
import requests

from seo_brief.fetch import USER_AGENT_TOKEN, Fetcher, load_offline

HTML = "<html><head><title>T</title></head><body><p>Hello world page.</p></body></html>"


class Resp:
    def __init__(self, status=200, body=HTML, ctype="text/html; charset=utf-8"):
        self.status_code = status
        self.content = body.encode("utf-8") if isinstance(body, str) else body
        self.text = self.content.decode("utf-8", errors="replace")
        self.headers = {"Content-Type": ctype}


class Session:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        result = self.routes.get(url, Resp(404, ""))
        if isinstance(result, Exception):
            raise result
        return result

    def urls(self):
        return [c[0] for c in self.calls]


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def make(routes, tmp_path=None, **kw):
    clock = Clock()
    f = Fetcher(
        cache_dir=tmp_path,
        session=Session(routes),
        sleep=clock.sleep,
        clock=clock.now,
        now=clock.now,
        **kw,
    )
    return f, clock


ROBOTS_OK = Resp(200, "User-agent: *\nDisallow: /private/\n", "text/plain")


def test_fetch_success():
    f, _ = make({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/p": Resp()})
    res = f.fetch("https://a.test/p")
    assert res.ok and "Hello" in res.html and not res.from_cache


def test_custom_user_agent_sent():
    f, _ = make({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/p": Resp()})
    f.fetch("https://a.test/p")
    assert all(USER_AGENT_TOKEN in h["User-Agent"] for _, h in f.session.calls)


def test_robots_disallow_blocks_without_fetching_page():
    f, _ = make({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/private/x": Resp()})
    res = f.fetch("https://a.test/private/x")
    assert res.error == "blocked by robots.txt"
    assert "https://a.test/private/x" not in f.session.urls()


def test_robots_fetched_once_per_host():
    routes = {
        "https://a.test/robots.txt": ROBOTS_OK,
        "https://a.test/1": Resp(),
        "https://a.test/2": Resp(),
    }
    f, _ = make(routes)
    f.fetch("https://a.test/1")
    f.fetch("https://a.test/2")
    assert f.session.urls().count("https://a.test/robots.txt") == 1


def test_missing_robots_allows():
    f, _ = make({"https://a.test/p": Resp()})  # robots.txt -> 404
    assert f.fetch("https://a.test/p").ok


def test_robots_server_error_is_conservative():
    f, _ = make({"https://a.test/robots.txt": Resp(503, ""), "https://a.test/p": Resp()})
    assert f.fetch("https://a.test/p").error == "blocked by robots.txt"


def test_robots_network_error_is_conservative():
    f, _ = make({"https://a.test/robots.txt": requests.ConnectionError("x")})
    assert not f.fetch("https://a.test/p").ok


def test_robots_can_be_disabled_explicitly():
    f, _ = make({"https://a.test/private/x": Resp()}, respect_robots=False)
    assert f.fetch("https://a.test/private/x").ok


def test_delay_between_requests_same_host():
    routes = {
        "https://a.test/robots.txt": ROBOTS_OK,
        "https://a.test/1": Resp(),
        "https://a.test/2": Resp(),
    }
    f, clock = make(routes, delay=2.0)
    f.fetch("https://a.test/1")
    f.fetch("https://a.test/2")
    assert len(clock.slept) >= 2
    assert all(s == pytest.approx(2.0) for s in clock.slept)


def test_no_delay_for_different_hosts():
    routes = {"https://a.test/p": Resp(), "https://b.test/p": Resp()}
    f, clock = make(routes, delay=2.0)
    f.fetch("https://a.test/p")
    f.fetch("https://b.test/p")
    # only the robots.txt -> page hop on the same host waits; hosts never wait on each other
    assert len(clock.slept) == 2


def test_http_error_reported():
    f, _ = make({"https://a.test/p": Resp(500, "boom")})
    res = f.fetch("https://a.test/p")
    assert res.error == "HTTP 500" and res.status == 500


def test_non_html_rejected():
    f, _ = make({"https://a.test/p": Resp(200, "%PDF", "application/pdf")})
    assert "not HTML" in f.fetch("https://a.test/p").error


def test_too_large_rejected():
    f, _ = make({"https://a.test/p": Resp(200, "x" * 100)}, max_bytes=10)
    assert f.fetch("https://a.test/p").error == "response too large"


def test_request_exception_handled():
    f, _ = make({"https://a.test/p": requests.Timeout("slow")})
    res = f.fetch("https://a.test/p")
    assert not res.ok and "Timeout" in res.error


@pytest.mark.parametrize("url", ["ftp://a.test/x", "file:///etc/passwd", "not a url", "https://"])
def test_invalid_urls_rejected(url):
    f, _ = make({})
    assert f.fetch(url).error == "unsupported or invalid URL"
    assert f.session.calls == []


def test_cache_roundtrip(tmp_path):
    routes = {"https://a.test/p": Resp()}
    f, _ = make(routes, tmp_path)
    first = f.fetch("https://a.test/p")
    second = f.fetch("https://a.test/p")
    assert not first.from_cache and second.from_cache
    assert f.session.urls().count("https://a.test/p") == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_expires(tmp_path):
    routes = {"https://a.test/p": Resp()}
    f, clock = make(routes, tmp_path, cache_ttl_hours=1)
    f.fetch("https://a.test/p")
    clock.t += 3601
    assert not f.fetch("https://a.test/p").from_cache


def test_cache_not_written_for_errors(tmp_path):
    f, _ = make({"https://a.test/p": Resp(404, "")}, tmp_path)
    f.fetch("https://a.test/p")
    assert not list(tmp_path.glob("*.json"))


def test_corrupt_cache_ignored(tmp_path):
    f, _ = make({"https://a.test/p": Resp()}, tmp_path)
    f.fetch("https://a.test/p")
    for p in tmp_path.glob("*.json"):
        p.write_text("{broken", encoding="utf-8")
    assert not f.fetch("https://a.test/p").from_cache


def test_cache_file_contents(tmp_path):
    f, _ = make({"https://a.test/p": Resp()}, tmp_path)
    f.fetch("https://a.test/p")
    data = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert data["url"] == "https://a.test/p" and "Hello" in data["html"]


def test_utf8_bangla_body_decoded():
    body = "<html><body><p>ইমেইল মার্কেটিং</p></body></html>"
    f, _ = make({"https://a.test/p": Resp(200, body)})
    assert "ইমেইল" in f.fetch("https://a.test/p").html


# -- offline --------------------------------------------------------------


def test_load_offline_reads_html_only(tmp_path):
    (tmp_path / "b.html").write_text("<p>b</p>", encoding="utf-8")
    (tmp_path / "a.htm").write_text("<p>a</p>", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("skip", encoding="utf-8")
    assert [n for n, _ in load_offline(tmp_path)] == ["a.htm", "b.html"]


def test_load_offline_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_offline(tmp_path / "nope")
