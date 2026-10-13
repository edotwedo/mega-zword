"""Chat-tab UI in dashboard.html: runs the page's own script in node with a tiny DOM stub."""

import json
import shutil
import subprocess
from importlib import resources

import pytest

SCRIPT = resources.files("megazword").joinpath("dashboard.html").read_text(encoding="utf-8")
SCRIPT = SCRIPT.split("<script>")[1].split("</script>")[0]
SCRIPT = SCRIPT[:SCRIPT.rindex("\nload();")]  # no network or timers

STUB = """
const elements = new Map();
const location = {search:''};
const document = {activeElement:null, title:'', addEventListener(){}, getElementById(id) {
  if (!elements.has(id)) elements.set(id, {id, innerHTML:'', textContent:'', value:'', hidden:false,
    disabled:false, dataset:{}, options:[], scrollTop:0, scrollHeight:0,
    setAttribute(k, v) { this[k] = v; }, addEventListener(){}, querySelectorAll(){ return []; },
    focus(){}, blur(){}, contains(){ return false; }, append(){}});
  return elements.get(id);
}};
const snap = () => Object.fromEntries([...elements].map(([k, v]) => [k,
  {html: v.innerHTML, text: v.textContent, hidden: v.hidden, pressed: v['aria-pressed'] ?? null}]));
const out = {};
"""


def run(exercise: str, tmp_path) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    program = tmp_path / "tabs.js"
    program.write_text(STUB + SCRIPT + exercise + "\nconsole.log(JSON.stringify(out));",
                       encoding="utf-8")
    result = subprocess.run([node, str(program)], capture_output=True, text=True,
                            encoding="utf-8", check=True, timeout=30)
    return json.loads(result.stdout.strip().splitlines()[-1])  # async tests print last


TABS = """[{id:'t1', title:'<b>Recipes</b>', ai:'claude', project:'kitchen',
  history:[{user:'<img src=x onerror=alert(1)>', answer:'Use **salt**', backend:'claude'}]},
 {id:'t2', title:'Plain', ai:'auto', project:'default', history:[]}]"""


def test_tabs_render_escaped_and_open_a_tab(tmp_path):
    out = run(f"""
state = {{backends: {{claude: true, codex: false, grok: true}}}};
setChatTabs({TABS}); renderChatAis();
setView('tab:t1');
out.tab = snap();
""", tmp_path)["tab"]
    strip = out["chat-tabs"]["html"]
    assert 'data-tab="t1"' in strip and 'data-tab="t2"' in strip
    assert "<b>Recipes</b>" not in strip and "&lt;b&gt;Recipes&lt;/b&gt;" in strip
    assert 'aria-pressed="true"' in strip  # the open tab is marked
    messages = out["chat-messages"]["html"]
    assert "<img" not in messages and "&lt;img" in messages
    assert "Use **salt**" in messages
    assert out["chat"]["hidden"] is False
    assert out["home-view"]["hidden"] is True and out["hive"]["hidden"] is True
    assert out["view-title"]["text"] == "<b>Recipes</b>"  # textContent, not HTML
    assert out["tab-home"]["pressed"] == "false"
    assert "AI: claude" in out["chat-info"]["text"]
    # Only installed AIs can be pinned to a new tab.
    ais = out["new-tab-ai"]["html"]
    assert 'value="claude"' in ais and 'value="grok"' in ais and 'value="codex"' not in ais


def test_closed_tab_falls_back_to_home(tmp_path):
    out = run(f"""
state = {{backends: {{}}}};
setChatTabs({TABS});
setView('tab:t2');
setChatTabs([]);  // closed in another window
out.after = snap();
setView('tab:missing');
out.missing = snap();
""", tmp_path)
    for key in ("after", "missing"):
        assert out[key]["home-view"]["hidden"] is False
        assert out[key]["chat"]["hidden"] is True
        assert out[key]["view-title"]["text"] == "Home"
    assert out["after"]["chat-tabs"]["html"] == ""


def test_empty_tab_and_busy_state(tmp_path):
    out = run(f"""
state = {{backends: {{}}}};
setChatTabs({TABS});
chatBusy.add('t2');
setView('tab:t2');
out.busy = snap();
""", tmp_path)["busy"]
    assert "No messages yet" in out["chat-messages"]["html"]
    assert out["chat-status"]["text"] == "Waiting for the AI…"
    assert "…" in out["chat-tabs"]["html"]


def test_page_has_the_tab_controls_with_labels():
    html = resources.files("megazword").joinpath("dashboard.html").read_text(encoding="utf-8")
    for needle in ('id="chat-tabs" aria-label="Chat tabs"', 'aria-label="New chat tab"',
                   'aria-label="AI for a new chat tab"', 'aria-label="Chat tab name"',
                   'id="chat-close"', 'aria-label="Your message"'):
        assert needle in html
    assert "confirm(" not in html  # browser dialogs block the app window; close uses two clicks


def test_floor_line_shows_ready_and_seated_names(tmp_path):
    out = run("""
renderFloor({floor: {ready: true, seats: [
  {name: 'claude', kind: 'cli', status: 'seated'}, {name: 'codex', kind: 'cli', status: 'out'},
  {name: '<b>x</b>', kind: 'http', status: 'seated'}, {name: 'grok', kind: 'cli', status: 'empty'}]}});
out.ready = snap().floor.html;
renderFloor({floor: {ready: false, seats: [{name: 'grok', kind: 'cli', status: 'empty'}]}});
out.empty = snap().floor.html;
renderFloor({});
out.missing = snap().floor;
""", tmp_path)
    assert ">ready<" in out["ready"] and "claude" in out["ready"]
    assert "codex" not in out["ready"] and "grok" not in out["ready"]  # only seated names
    assert "<b>x</b>" not in out["ready"] and "&lt;b&gt;x&lt;/b&gt;" in out["ready"]
    assert "not ready" in out["empty"] and "none" in out["empty"]
    assert out["missing"]["html"] == ""  # older servers without `floor` show nothing


def test_deep_link_opens_a_tab_once(tmp_path):
    out = run(f"""
location.hash = '#tab-t1';
const realFetch = async () => ({{ok: true, json: async () => ({{tabs: {TABS}, backends: {{}}, out: {{}},
  project: 'p', projects: ['p'], runs: [], jobs: [], settings: null}})}});
globalThis.fetch = realFetch;
for (const name of ['renderSettings','renderPlans','renderSentinel','renderRoute','renderChart',
  'renderTrend','renderRuns','renderMem','renderAnswers','renderComparePicks','renderAdvice'])
  eval(name + ' = () => {{}}');  // function declarations are module-local in node
load().then(() => {{ out.first = snap();
  setView('home'); return load(); }}).then(() => {{ out.second = snap();
  console.log(JSON.stringify(out)); process.exit(0); }});
""", tmp_path)
    assert out["first"]["chat"]["hidden"] is False
    assert out["first"]["view-title"]["text"] == "<b>Recipes</b>"
    assert out["second"]["home-view"]["hidden"] is False  # a later refresh doesn't jump back
