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
                   'id="chat-close"', 'id="chat-new-session"', 'aria-label="Your message"', 'id="hive-floor"'):
        assert needle in html
    assert "confirm(" not in html  # browser dialogs block the app window; close uses two clicks


def test_plus_preserves_original_history_and_separate_drafts(tmp_path):
    out = run(f"""
setChatTabs({TABS}); setView('tab:t1');
$('chat-input').value = 'unfinished original draft';
post = async () => ({{id:'t3'}});
reloadChatTabs = async () => setChatTabs([...chatTabs, {{id:'t3',title:'New',ai:'auto',project:'default',history:[]}}]);
$('new-tab').onclick().then(() => {{
  out.newDraft = $('chat-input').value;
  $('chat-input').value = 'new chat draft'; setView('tab:t1');
  out.originalDraft = $('chat-input').value; out.originalHistory = $('chat-messages').innerHTML;
  setView('tab:t3'); out.restoredNewDraft = $('chat-input').value;
  console.log(JSON.stringify(out)); process.exit(0);
}});
""", tmp_path)
    assert out['newDraft'] == ''
    assert out['originalDraft'] == 'unfinished original draft'
    assert 'Use **salt**' in out['originalHistory']
    assert out['restoredNewDraft'] == 'new chat draft'


def test_delete_chat_removes_selected_tab_without_clearing_another(tmp_path):
    out = run(f"""
setChatTabs({TABS}); setView('tab:t1');
post = async (path, body) => {{out.deleted = body.id; chatTabs = chatTabs.filter(t => t.id !== body.id);}};
reloadChatTabs = async () => setChatTabs(chatTabs);
deleteChat('t2').then(() => {{
  out.view = currentView; out.history = $('chat-messages').innerHTML;
  out.remaining = chatTabs.map(t => t.id);
  console.log(JSON.stringify(out)); process.exit(0);
}});
""", tmp_path)
    assert out['deleted'] == 't2'
    assert out['remaining'] == ['t1']
    assert out['view'] == 'tab:t1'
    assert 'Use **salt**' in out['history']


def test_hive_send_requests_reply_without_separate_start(tmp_path):
    out = run("""
$('room-input').value = 'What is next?'; $('room-turn-cap').value = '12';
post = async (path, body) => {out.path = path; out.body = body;};
loadRoom = async () => {};
$('room-send').onclick().then(() => {
  out.input = $('room-input').value;
  console.log(JSON.stringify(out)); process.exit(0);
});
""", tmp_path)
    assert out['path'] == '/api/room/say'
    assert out['body']['start'] is True
    assert out['body']['text'] == 'What is next?'
    assert out['input'] == ''


def test_session_marker_note_and_busy_reset(tmp_path):
    out = run("""
setChatTabs([{id:'t1', title:'Work', ai:'claude', project:'p', history:[],
  session_id:'abc', session_backend:'claude', session_note:'Previous session unavailable; started a new session.'}]);
setView('tab:t1'); out.kept = snap();
chatBusy.add('t1'); renderChat(chatTab('t1'));
out.disabled = $('chat-new-session').disabled;
out.busy = snap();
""", tmp_path)
    assert "session kept (claude)" in out["kept"]["chat-info"]["text"]
    assert "Previous session unavailable" in out["kept"]["chat-status"]["text"]
    assert out["disabled"] is True


def test_new_session_button_posts_reset_and_refreshes(tmp_path):
    out = run("""
setChatTabs([{id:'t1', title:'Work', ai:'codex', project:'p', history:[], session_id:'abc'}]);
setView('tab:t1'); $('chat-input').value = 'draft';
post = async (url, body) => { out.request = {url, body}; return {}; };
reloadChatTabs = async () => { setChatTabs([{id:'t1', title:'Work', ai:'codex', project:'p',
  history:[], session_id:'', session_note:'New session started.'}]); };
$('chat-new-session').onclick().then(() => {
  out.after = snap(); out.input = $('chat-input').value;
  out.busy = chatBusy.has('t1'); console.log(JSON.stringify(out)); process.exit(0);
});
""", tmp_path)
    assert out["request"] == {"url": "/api/tabs/new-session", "body": {"id": "t1"}}
    assert "session kept" not in out["after"]["chat-info"]["text"]
    assert out["after"]["chat-status"]["text"] == "New session started."
    assert out["input"] == "" and out["busy"] is False


def test_floor_line_shows_ready_and_seated_names(tmp_path):
    out = run("""
renderFloor({floor: {ready: true, seats: [
  {name: 'claude', kind: 'cli', status: 'seated'}, {name: 'codex', kind: 'cli', status: 'out'},
  {name: '<b>x</b>', kind: 'http', status: 'seated'}, {name: 'grok', kind: 'cli', status: 'empty'}]}});
out.ready = snap().floor.html; out.hiveReady = snap()['hive-floor'].html;
renderFloor({floor: {ready: false, seats: [{name: 'grok', kind: 'cli', status: 'empty'}]}});
out.empty = snap().floor.html;
renderFloor({});
out.missing = snap().floor; out.hiveMissing = snap()['hive-floor'].html;
""", tmp_path)
    assert out["hiveReady"] == out["ready"]  # Hive panel shows the same line as Home
    assert out["hiveMissing"] == ""
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
