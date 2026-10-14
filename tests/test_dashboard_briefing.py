"""Briefing reads never invoke a backend; writes use dashboard authentication."""

import json
import urllib.error
import urllib.request
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from megazword import briefing
from tests.test_dashboard import app, server, _post


def test_report_and_read_round_trip_over_http(server):
    base, app = server
    report = {"seat": "testlog-14", "doing": "tests", "next": "publish"}
    with pytest.raises(urllib.error.HTTPError) as error:
        _post(base + "/api/briefing/report", report)
    assert error.value.code == 403
    saved = json.loads(_post(base + "/api/briefing/report", report, app.token).read())
    assert saved["seat"] == "testlog-14"
    data = json.loads(urllib.request.urlopen(base + "/api/briefing", timeout=5).read())
    assert data["cards"][0]["doing"] == "tests"
    assert "Next: publish" in data["text"]
    assert data["camera"]["status"] == "off" and not app.jobs


def test_camera_control_requires_token_and_boolean(server):
    base, app = server
    with pytest.raises(urllib.error.HTTPError) as error:
        _post(base + "/api/briefing/camera", {"enabled": True})
    assert error.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as error:
        _post(base + "/api/briefing/camera", {"enabled": "false"}, app.token)
    assert error.value.code == 400
    assert app.camera.view()["status"] == "off"


def test_camera_actions_and_shutdown_use_the_same_watcher(app):
    class FakeCamera:
        status = "off"
        event = 0

        def start(self):
            self.status = "watching"

        def stop(self):
            self.status = "off"

        def view(self):
            return {"status": self.status, "event": self.event, "present": None, "error": ""}

    app.camera = FakeCamera()
    assert app.briefing_camera({"enabled": True})["camera"]["status"] == "watching"
    app.camera.event = 1
    assert app.briefing_view()["camera"]["event"] == 1
    app.shutdown()
    assert app.briefing_view()["camera"]["status"] == "off"


def test_dialog_opens_once_per_new_return_and_renders_reports_as_text(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    html = (Path(__file__).parents[1] / "src/megazword/dashboard.html").read_text(encoding="utf-8")
    script = re.search(r"<script>(.*?)</script>", html, re.S)[1]
    script = script[:script.rindex("\nload();")]
    stub = """
const elements = new Map();
const location = {search:''};
const document = {activeElement:null, addEventListener(){}, getElementById(id) {
  if (!elements.has(id)) elements.set(id, {innerHTML:'', dataset:{}, open:false,
    setAttribute(){}, showModal(){this.open=true;}, addEventListener(){},
    querySelectorAll(){return []}, append(){}});
  return elements.get(id);
}};
"""
    exercise = """
function check(value) { if (!value) throw new Error('briefing assertion failed'); }
const data = {text:'<script>untrusted report</script>', camera:{status:'watching',event:1,present:true,error:''}};
renderBriefing(data); check(!$('brief-dialog').open);
data.camera.event=2; renderBriefing(data); check($('brief-dialog').open);
check($('brief-text').textContent===data.text && $('brief-text').innerHTML==='');
$('brief-dialog').open=false; renderBriefing(data); check(!$('brief-dialog').open);
data.camera.event=1; renderBriefing(data); check(!$('brief-dialog').open);
data.camera.event=2; renderBriefing(data); check(!$('brief-dialog').open);
data.camera.event=3; renderBriefing(data); check($('brief-dialog').open);
"""
    program = tmp_path / "briefing-ui.js"
    program.write_text(stub + script + exercise, encoding="utf-8")
    result = subprocess.run([node, str(program)], capture_output=True, text=True,
                            encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
