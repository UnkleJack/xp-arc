"""Regression tests pinning the Apache 2.0 relicense (2026-08-23).

These tests guard against the license drifting back to a MIT or BSL
assertion on any of the nine surfaces that declare it. They match specific
*assertion* phrasings ("released under the MIT License", "under the
**Business Source License**") rather than bare substring "MIT" / "BSL",
because several documents legitimately reference the superseded licenses in
historical changelog entries (e.g. CONSTITUTION.MD's v1.5 changelog line,
which correctly says "MIT license" describing what v1.5 *was*). Forbidding
the bare word would make honest changelogs untestable.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Assertion phrasings that would mean the license reverted to MIT or BSL as
# the LIVE license. Historical/changelog mentions of "MIT" or "BSL" alone do
# not match these and are allowed.
FORBIDDEN_LIVE_ASSERTIONS = [
    re.compile(r"released under the \*?\*?MIT License", re.IGNORECASE),
    re.compile(r"is released under the \*?\*?Business Source License", re.IGNORECASE),
    re.compile(r"under the \*?\*?Business Source License", re.IGNORECASE),
    re.compile(r"^\*\*License:\*\*\s*MIT\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\*\*License:\*\*\s*BSL", re.IGNORECASE | re.MULTILINE),
    re.compile(r'license\s*=\s*\{text\s*=\s*"MIT"\}', re.IGNORECASE),
    re.compile(r'license\s*=\s*\{text\s*=\s*"BSL', re.IGNORECASE),
]

SURFACES = [
    "LICENSE",
    "NOTICE",
    "pyproject.toml",
    "CONSTITUTION.MD",
    "LEGAL.md",
    "WHITEPAPER.md",
    "README.md",
    "ARCHITECTURE.md",
    "Gauntlet_CONSTITUTION.md",
]


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def test_license_file_is_apache_2_0():
    text = _read("LICENSE")
    assert "Apache License" in text
    assert "Version 2.0" in text
    assert "MIT License" not in text


def test_notice_file_exists_with_trademark_reservation():
    text = _read("NOTICE")
    for mark in ["XP-Arc", "DRAGON", "Aboyeur", "Zoran's Law", "SpaZzMatiC"]:
        assert mark in text, f"NOTICE missing trademark reservation for {mark}"
    assert "Apache License" in text


def test_pyproject_declares_apache_license():
    text = _read("pyproject.toml")
    assert 'license = {text = "Apache-2.0"}' in text
    assert "Apache Software License" in text


def test_constitution_asserts_apache_as_live_license():
    text = _read("CONSTITUTION.MD")
    assert "Apache License, Version 2.0" in text or "Apache License 2.0" in text
    assert "trademark-backed certification" in text
    # Article XI 11.1 item 2 (the live monetization list) must no longer
    # describe BSL-protected deployments. We isolate that specific list item
    # rather than banning the phrase document-wide, because the v1.6
    # changelog entry legitimately quotes the superseded wording to describe
    # what changed ("changed from 'BSL-protected stamped deployments' to...").
    section_11_1 = text.split("### Section 11.1", 1)[1].split("### Section 11.2", 1)[0]
    assert "BSL-protected stamped deployments" not in section_11_1


def test_legal_md_asserts_apache():
    text = _read("LEGAL.md")
    assert "Apache License, Version 2.0" in text


def test_whitepaper_asserts_apache():
    text = _read("WHITEPAPER.md")
    assert "**License:** Apache-2.0" in text
    assert "Apache License, Version 2.0" in text


def test_readme_asserts_apache():
    text = _read("README.md")
    assert "Apache License 2.0" in text


def test_architecture_version_table_asserts_apache():
    text = _read("ARCHITECTURE.md")
    assert "Apache 2.0 license" in text


def test_gauntlet_constitution_asserts_apache():
    text = _read("Gauntlet_CONSTITUTION.md")
    assert "**License:** Apache-2.0" in text


def test_no_surface_reasserts_mit_or_bsl_as_live_license():
    for surface in SURFACES:
        text = _read(surface)
        for pattern in FORBIDDEN_LIVE_ASSERTIONS:
            match = pattern.search(text)
            assert not match, (
                f"{surface} reasserts a superseded license via pattern "
                f"{pattern.pattern!r}: {match.group(0)!r}"
            )
