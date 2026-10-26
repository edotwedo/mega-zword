from megazword import repo_map


def _repo(tmp_path):
    (tmp_path / "core.py").write_text(
        "class Engine:\n    def start(self, speed):\n        pass\n    def _hidden(self):\n        pass\n"
        "def helper_tool(x):\n    return x\n", encoding="utf-8")
    (tmp_path / "user.py").write_text(
        "from core import Engine, helper_tool\nEngine().start(1)\nhelper_tool(Engine)\n"
        "def lonely_thing():\n    pass\n", encoding="utf-8")
    (tmp_path / "app.ts").write_text(
        "export function pickJoke(list: string[]) {}\nconst localOnly = 1;\n"
        "export const TOPICS = {};\ninterface Bit {}\n", encoding="utf-8")
    nm = tmp_path / "node_modules" / "dep"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("export function vendored() {}\n", encoding="utf-8")


def test_symbols_lists_public_defs_and_methods():
    text = "class A:\n    def go(self, x):\n        def inner():\n            pass\n    def _no(self):\n        pass\n"
    assert repo_map.symbols(text, "py") == [(1, "A", "class A"), (2, "go", "  def go(self, x)")]


def test_symbols_reads_ts_exports_and_skips_local_consts():
    text = "export function pickJoke(a) {}\nconst hidden = 1;\nexport const TOPICS = {};\ninterface Bit {}\n"
    names = [name for _, name, _ in repo_map.symbols(text, "js")]
    assert names == ["pickJoke", "TOPICS", "Bit"]


def test_build_ranks_used_files_first_and_skips_vendor(tmp_path):
    _repo(tmp_path)
    text = repo_map.build(tmp_path)
    assert text.index("core.py:") < text.index("user.py:")
    assert "  2:   def start(self, speed)" in text
    assert "_hidden" not in text and "vendored" not in text and "localOnly" not in text


def test_focus_moves_matching_file_to_top(tmp_path):
    _repo(tmp_path)
    assert repo_map.build(tmp_path, focus=["joke"]).startswith("app.ts:")


def test_build_respects_size_cap(tmp_path):
    _repo(tmp_path)
    text = repo_map.build(tmp_path, max_chars=60)
    assert len(text) < 120
    assert "more files not shown" in text


def test_map_command_prints(tmp_path, capsys):
    _repo(tmp_path)
    from megazword.cli import build_parser
    args = build_parser().parse_args(["map", "--root", str(tmp_path), "engine"])
    assert repo_map.command(args) == 0
    assert capsys.readouterr().out.startswith("core.py:")


CS = """namespace RobinCode
{
    public sealed partial class RobinForm : Form
    {
        public RobinForm()
        {
            if (ready) { Start(); }
        }
        public async Task<string> RunPromptStreamAsync(string prompt, CancellationToken ct)
        {
            return await Send(prompt);
        }
        private void Hidden() { }
        internal static int Count<T>(List<T> items) => items.Count;
    }
    private class Secret { }
    public interface IClient { }
    public record Reply(string Text);
}
"""


def test_symbols_reads_csharp_types_and_non_private_methods():
    names = [name for _, name, _ in repo_map.symbols(CS, "cs")]
    assert names == ["RobinForm", "RobinForm", "RunPromptStreamAsync", "Count", "IClient", "Reply"]


def test_csharp_signature_keeps_parameters():
    sigs = {name: sig for _, name, sig in repo_map.symbols(CS, "cs")}
    assert sigs["RunPromptStreamAsync"].endswith("RunPromptStreamAsync(string prompt, CancellationToken ct)")


def test_build_maps_csharp_and_skips_bin_obj(tmp_path):
    (tmp_path / "RobinForm.cs").write_text(CS, encoding="utf-8")
    (tmp_path / "Program.cs").write_text(
        "static class Program {\n    static void Main() { new RobinForm(); }\n}\n", encoding="utf-8")
    for d in ("bin", "obj"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "Gen.cs").write_text("public class Generated { }\n", encoding="utf-8")
    text = repo_map.build(tmp_path)
    assert "RobinForm.cs:" in text and "RunPromptStreamAsync" in text
    assert "Generated" not in text and "Hidden" not in text and "Secret" not in text
