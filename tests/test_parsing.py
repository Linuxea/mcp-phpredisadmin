"""Unit tests for the pure parsing helpers (no network needed)."""

from __future__ import annotations

from pra_mcp.parsing import (
    extract_csrf,
    extract_keys,
    find_server_select,
    parse_server_options,
    strip_html,
)

# Shaped like the sidebar index.php emits: keys live in hrefs,
# "&" is escaped as "&amp;" in the HTML attributes, key names are urlencoded.
SIDEBAR_HTML = """
<html><body>
<ul>
<li><input type="checkbox" name="checked_keys" value="user:1"/>
<a href="?view&amp;s=0&amp;d=0&amp;key=user%3A1" title="user:1">user:1<span class="info">(3)</span></a></li>
<li><a href="?view&amp;s=0&amp;d=0&amp;key=user%3A2">user:2</a></li>
<li><a href="?view&amp;s=0&amp;d=0&amp;key=session%3Aabc">session:abc</a></li>
<li><a href="?view&amp;s=0&amp;d=0&amp;key=user%3A1">user:1 (duplicate href)</a></li>
</ul>
</body></html>
"""


class TestExtractKeys:
    def test_extracts_and_unquotes(self):
        keys = extract_keys(SIDEBAR_HTML)
        assert keys == ["session:abc", "user:1", "user:2"]

    def test_no_keys(self):
        assert extract_keys("<html><body>empty</body></html>") == []

    def test_key_with_spaces_stays_plus(self):
        # Documents current behaviour: PHP urlencode() encodes a space as "+",
        # and urllib.parse.unquote() does NOT decode "+" — so such a key
        # round-trips with a "+" in it. If this test starts failing after an
        # intended fix (unquote_plus), update the expectation deliberately.
        html = '<a href="?view&amp;s=0&amp;d=0&amp;key=foo+bar">x</a>'
        assert extract_keys(html) == ["foo+bar"]


class TestStripHtml:
    def test_removes_script_and_style(self):
        html = "<style>.a{color:red}</style><script>alert(1)</script><p>hi</p>"
        assert strip_html(html) == "hi"

    def test_unescapes_entities_and_squeezes_spaces(self):
        html = "<td>a&nbsp;&amp;&nbsp;b</td>  <td>c</td>"
        assert strip_html(html) == "a\xa0&\xa0b c"

    def test_empty(self):
        assert strip_html("") == ""


class TestServerSelect:
    HTML = """
    <select id="server">
    <option value="0" selected="selected">localhost:6379</option>
    <option value="1">starchat</option>
    </select>
    """

    def test_finds_select(self):
        assert find_server_select(self.HTML) is not None

    def test_missing_select(self):
        assert find_server_select("<p>no select here</p>") is None

    def test_parses_options(self):
        from pra_mcp.parsing import ServerOption

        opts = parse_server_options(find_server_select(self.HTML))
        assert opts == [
            ServerOption(value="0", selected=True, name="localhost:6379"),
            ServerOption(value="1", selected=False, name="starchat"),
        ]

    def test_unescapes_names(self):
        select = '<option value="2">a&amp;b</option>'
        (opt,) = parse_server_options(select)
        assert opt.name == "a&b"


class TestExtractCsrf:
    def test_found(self):
        html = '<input type="hidden" name="csrf" value="abc123" />'
        assert extract_csrf(html) == "abc123"

    def test_absent(self):
        assert extract_csrf("<form></form>") is None
