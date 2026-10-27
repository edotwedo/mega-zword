"""B15: light rules for AIs that train on prompts."""

from dataclasses import dataclass

from megazword.backends import Backend
from megazword.cli import candidates
from megazword.config import DEFAULT_ROUTE
from megazword.guard import MASK, scrub
from megazword.rater import Rating


def test_scrub_removes_obvious_secrets_and_private_paths():
    text = ("key sk-abcdefghijklmnopqrstuv and ghp_" + "a" * 36 + "\n"
            "MISTRAL_API_KEY=abc123xyz\npassword: hunter22\n"
            "see C:\\Users\\mrmar\\.claude\\.credentials.json\n"
            "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----\n")
    out = scrub(text)
    for secret in ("sk-abc", "ghp_", "abc123xyz", "hunter22", ".credentials.json", "MIIE"):
        assert secret not in out
    assert out.count(MASK) >= 6


def test_scrub_leaves_normal_text_alone():
    text = "token budget: keep replies short.\nRename these 12 files and fix the typo."
    assert scrub(text) == text


@dataclass
class Fake(Backend):
    seen: str = ""

    def _run(self, prompt):
        self.seen = prompt
        return "ok"


def test_trains_on_data_backend_gets_scrubbed_prompt_others_do_not():
    mistral, claude = Fake("mistral", trains_on_data=True), Fake("claude")
    prompt = "use MISTRAL_API_KEY=abc123xyz please"
    mistral.run(prompt)
    claude.run(prompt)
    assert "abc123xyz" not in mistral.seen and "abc123xyz" in claude.seen


def test_trainers_go_first_for_easy_only():
    backends = {"grok": Fake("grok"), "mistral": Fake("mistral", trains_on_data=True),
                "claude": Fake("claude"), "codex": Fake("codex")}
    route = {"easy": ["grok", "mistral"], "medium": ["codex"], "hard": ["claude"]}
    easy = candidates(Rating("easy", "", "rule"), route, backends)
    assert [b.name for b in easy][:2] == ["mistral", "grok"]
    hard = candidates(Rating("hard", "", "rule"), route, backends)
    assert "mistral" not in [b.name for b in hard]


def test_default_routes_leave_out_spent_tencent_grants():
    spent = {
        "tencent-glm-5.3-flash", "tencent-glm-5.3",
        "tencent-kimi-k2.7-code", "tencent-kimi-k3",
        "tencent-deepseek-v4-pro", "tencent-deepseek-v4-flash-vision-exp",
    }
    assert all(spent.isdisjoint(names) for names in DEFAULT_ROUTE.values())
