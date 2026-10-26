from pathlib import Path
import json
import pytest

from tools.shortvid import shortvid

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "tools" / "shortvid" / "scripts"

def test_shortvid_scripts_pricing():
    """All Spanda shortvid scripts must accurately reflect the $29.99 live price."""
    assert SCRIPTS_DIR.exists(), f"{SCRIPTS_DIR} must exist"
    scripts = list(SCRIPTS_DIR.glob("*.json"))
    assert len(scripts) >= 3, "At least three Spanda scripts must be provided"
    
    for s_path in scripts:
        data = json.loads(s_path.read_text(encoding="utf-8"))
        assert data.get("brand") == "Spanda"
        full_text = " ".join([sc.get("text", "") + " " + sc.get("sub", "") for sc in data.get("scenes", [])])
        full_text += " " + data.get("caption", "")
        if "29" in full_text:
            assert "29.99" in full_text, f"{s_path.name} must mention 29.99 if price is stated"
            assert "29.00" not in full_text, f"{s_path.name} must not contain stale 29.00"

def test_shortvid_slide_rendering(tmp_path):
    """Test generating carousel slides without requiring external video encoding."""
    script_file = SCRIPTS_DIR / "spanda-001.json"
    data = json.loads(script_file.read_text(encoding="utf-8"))
    theme = shortvid.Theme(data.get("theme", {}))
    brand = data.get("brand", "")
    scenes = data.get("scenes", [])
    highlight = set(data.get("highlight", []))
    assert len(scenes) > 0

    img = shortvid.slide(scenes[0], theme, script_file.parent, brand, 1, len(scenes), highlight)
    assert img.size == (shortvid.SW, shortvid.SH)
    slide_path = tmp_path / "slide-1.png"
    img.save(slide_path)
    assert slide_path.exists()
    assert slide_path.stat().st_size > 1000
