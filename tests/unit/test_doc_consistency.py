"""CI consistency tests verifying DOC-03 rule.

Rule DOC-03: Defaults in config/defaults.toml and docs/CONFIGURATION.md must match.
"""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_doc_03_config_docs_consistency() -> None:
    """Verify that all sections in config/defaults.toml are documented in docs/CONFIGURATION.md."""
    defaults_path = REPO_ROOT / "config" / "defaults.toml"
    docs_path = REPO_ROOT / "docs" / "CONFIGURATION.md"

    assert defaults_path.exists(), "config/defaults.toml must exist"
    assert docs_path.exists(), "docs/CONFIGURATION.md must exist"

    with defaults_path.open("rb") as f:
        defaults_data = tomllib.load(f)

    docs_content = docs_path.read_text(encoding="utf-8")

    # Verify schema version
    assert f"schema_version = {defaults_data.get('schema_version')}" in docs_content

    # Verify that every primary section exists in docs/CONFIGURATION.md
    expected_sections = [
        "camera",
        "tracking",
        "loop",
        "filters",
        "pointer",
        "click",
        "scroll",
        "zoom",
        "fingers",
        "session",
        "cockpit",
        "ui",
        "accessibility",
        "blackbox",
        "privacy",
    ]

    for section in expected_sections:
        assert section in defaults_data, f"Section '{section}' missing from defaults.toml"
        assert f"| {section} " in docs_content or f"| {section}." in docs_content, (
            f"Section '{section}' not documented in docs/CONFIGURATION.md table"
        )

    # Verify non-negotiable safety invariant: privacy network must be false
    assert defaults_data["privacy"]["network"] is False
    assert "network" in docs_content
