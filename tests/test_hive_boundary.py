"""hive/ is internal Hive tooling and must never reach the shipped package."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_package_is_built_from_src_only():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert not (ROOT / "src" / "hive").exists()


def test_shipped_code_never_imports_hive():
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "import hive" not in text and "from hive" not in text, path
