"""Accessibility contracts for the static page and rendered dashboard controls."""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import shutil
import subprocess

import pytest

HTML = (Path(__file__).parents[1] / 'src/megazword/dashboard.html').read_text(encoding='utf-8')
SCRIPT = re.search(r'<script>(.*?)</script>', HTML, re.S)[1]
CSS = re.search(r'<style>(.*?)</style>', HTML, re.S)[1]


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def by_id(self, name):
        return next(attrs for _, attrs in self.elements if attrs.get('id') == name)


def test_landmarks_labels_and_live_regions():
    page = Markup(HTML)
    tags = [tag for tag, _ in page.elements]
    assert tags.count('header') == tags.count('main') == tags.count('h1') == 1
    headings = [int(tag[1]) for tag in tags if re.fullmatch(r'h[1-6]', tag)]
    assert all(b <= a + 1 for a, b in zip(headings, headings[1:]))
    assert headings.count(3) == 3
    for name in ('prompt', 'note'):
        assert page.by_id(name)['aria-label']
    for name in ('jobs', 'toast'):
        assert page.by_id(name)['aria-live'] == 'polite'
    assert page.by_id('toast')['role'] == 'status'
    assert page.by_id('mem')['tabindex'] == '0'
    assert not any(int(a.get('tabindex', '0')) > 0 for _, a in page.elements)


@pytest.fixture(scope='module')
def rendered():
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    # Evaluate the actual renderers, without starting networking or timers.
    script = SCRIPT[:SCRIPT.rindex('\nload();')]
    stub = '''
const elements = new Map();
const document = {activeElement:null, addEventListener(){}, getElementById(id) {
  if (!elements.has(id)) elements.set(id, {innerHTML:'', dataset:{}, contains(){return false},
    addEventListener(){}, querySelectorAll(){return []}, append(){}});
  return elements.get(id);
}};
'''
    exercise = '''
state = {backends:{codex:true, claude:true}};
$('compare').checked = true;
renderComparePicks();
renderSettings({ais:['codex','claude'],route:{easy:['codex','claude'],medium:[],hard:[]},timeouts:{},limits:{log_lines:20,memory_lines:20},quality_check:false});
renderPlans({usage:[{service:'codex',verdict:'free',windows:[{name:'weekly',used:42,elapsed:50,known:true}]}]});
renderChart({runs_24h:{codex:{ok:2,failed:1,rejected:0,est_tokens:90}}});
renderTrend({trend:[{day:'2026-10-11',runs:{codex:3},ok:{codex:2}}]});
console.log(JSON.stringify(Object.fromEntries([...elements].map(([k,v])=>[k,v.innerHTML]))));
'''
    result = subprocess.run([node, '-e', stub + script + exercise], capture_output=True,
                            text=True, encoding='utf-8', check=True, timeout=30)
    return {k: Markup(v) for k, v in json.loads(result.stdout).items()}


def test_dynamic_compare_and_settings_labels(rendered):
    picks = [a for tag, a in rendered['cmppicks'].elements if tag == 'input']
    assert {a['aria-label'] for a in picks} == {'Compare codex', 'Compare claude'}
    for level in ('easy', 'medium', 'hard'):
        row = rendered['setting-route-' + level]
        labels = [a['aria-label'] for tag, a in row.elements if tag == 'button']
        for name in ('codex', 'claude'):
            for direction in ('up', 'down'):
                assert f'move {name} {direction} in {level}' in labels
        for tag, attrs in row.elements:
            if tag == 'input':
                assert f'in {level} route' in attrs['aria-label']


def test_chart_and_meter_text_alternatives(rendered):
    meter = next(a for _, a in rendered['plans'].elements if a.get('role') == 'meter')
    assert meter['aria-label'] == 'codex weekly usage'
    assert (meter['aria-valuemin'], meter['aria-valuemax'], meter['aria-valuenow']) == ('0', '100', '42')
    assert meter['aria-valuetext'] == '42% used; 50% of window elapsed'
    chart = next(a for _, a in rendered['chart'].elements if a.get('role') == 'img')
    assert chart['aria-label'] == 'codex: 2 successful, 1 failed or rejected runs; 90 estimated tokens'
    trend = next(a for tag, a in rendered['trend'].elements if tag == 'svg')
    assert '2026-10-11: codex 3 runs, 2 successful' in trend['aria-label']


def luminance(color):
    channels = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + .05) / (dark + .05)


TOKENS = dict(re.findall(r'--([\w-]+):\s*(#[0-9a-fA-F]{6})', CSS))
SURFACES = ('bg', 'panel', 'field', 'button', 'inset')
TEXT = ('text', 'dim', 'accent', 'ok', 'warn', 'bad', 'info', 'claude', 'codex', 'grok', 'local')


@pytest.mark.parametrize('foreground', TEXT)
@pytest.mark.parametrize('background', SURFACES)
def test_text_token_contrast(foreground, background):
    assert contrast(TOKENS[foreground], TOKENS[background]) >= 4.5


@pytest.mark.parametrize('foreground,background', [('on-accent', 'accent'), ('on-bad', 'bad')])
def test_colored_button_and_toast_contrast(foreground, background):
    assert contrast(TOKENS[foreground], TOKENS[background]) >= 4.5


@pytest.mark.parametrize('background', SURFACES)
def test_ui_border_and_focus_contrast(background):
    for foreground in ('line', 'accent'):
        assert contrast(TOKENS[foreground], TOKENS[background]) >= 3


def test_focus_touch_and_reduced_motion():
    assert re.search(r':focus-visible\s*\{[^}]*outline:2px solid var\(--accent\)', CSS)
    assert re.search(r'@media\s*\(max-width: 500px\)\s*\{\s*button, select, input, textarea, summary\s*\{\s*min-width:44px; min-height:44px;', CSS)
    assert re.search(r'@media\s*\(prefers-reduced-motion: reduce\)\s*\{\s*\.spin\s*\{\s*animation:none;', CSS)
    assert 'opacity: .45' not in CSS and 'opacity: .7' not in CSS
    # A character-only global shortcut interferes with speech input (WCAG 2.1.4).
    shortcut = SCRIPT[SCRIPT.index('if (e.key === "/"'):].split('{', 1)[0]
    assert '&& e.altKey' in shortcut
