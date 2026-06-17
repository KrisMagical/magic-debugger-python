from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_license_uses_pep621_object_form():
    content = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'license = "MIT"' not in content
    assert 'license = { file = "LICENSE" }' in content or 'license = { text = "MIT" }' in content


def test_license_file_is_included_in_manifest():
    assert (ROOT / "LICENSE").exists()

    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "include LICENSE" in manifest
