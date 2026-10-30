import json
import re

from bambuddy import web


def test_render_page_embeds_boot_safely(tmp_path, monkeypatch):
    template = '<script id="bambuddy-boot" type="application/json">__BAMBUDDY_BOOT__</script>'
    monkeypatch.setattr(web, "files", lambda _: tmp_path)
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text(template)

    html = web.render_page({"fileName": "</script><b>"})
    embedded = re.search(r'json">(.*)</script>$', html).group(1)
    assert "</script><b>" not in embedded
    assert json.loads(embedded) == {"fileName": "</script><b>"}
