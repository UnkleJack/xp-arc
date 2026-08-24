"""
License conformance tests.

Pins the 2026-08-19 Apache 2.0 relicense ruling across every surface that
states XP-Arc's license. Each test fails if its surface reasserts MIT or
BSL as the *live* license. Historical changelog/version-history mentions
of MIT (e.g. "v1.5: ... MIT license.") are not matched -- these tests only
match present-tense license assertion phrasings ("License: MIT",
"released under the MIT License", "License:` `MIT`" in a metadata header,
etc.), not backward-looking changelog prose.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Phrasings that assert MIT/BSL as the CURRENT license. Deliberately does not
# match generic substrings like "MIT" inside a changelog sentence describing
# a past version -- each pattern requires an assertion verb/colon adjacent
# to the license name.
_LIVE_MIT_ASSERTION = re.compile(
    r"(released under (the )?\*{0,2}MIT|License:\**\s*MIT\b|Version 1\.5 \| MIT License)",
    re.IGNORECASE,
)
_LIVE_BSL_ASSERTION = re.compile(
    r"(released under (the )?\*{0,2}BSL|License:\**\s*BSL|BSL[- ]protected stamped deployments)",
    re.IGNORECASE,
)


def _read(relpath):
    path = PROJECT_ROOT / relpath
    assert path.exists(), f"{relpath} does not exist"
    return path.read_text(encoding="utf-8")


def _assert_no_live_mit_or_bsl(text, surface):
    mit_hit = _LIVE_MIT_ASSERTION.search(text)
    assert mit_hit is None, (
        f"{surface} still asserts MIT as the live license: {mit_hit.group(0)!r}"
    )
    bsl_hit = _LIVE_BSL_ASSERTION.search(text)
    assert bsl_hit is None, (
        f"{surface} still asserts BSL as the live license: {bsl_hit.group(0)!r}"
    )


def test_license_file_is_apache():
    text = _read("LICENSE")
    assert "Apache License" in text
    assert "Version 2.0" in text
    assert "Copyright 2026 David J. Riedl" in text


def test_notice_file_exists_with_trademark_reservation():
    text = _read("NOTICE")
    assert "Apache License, Version 2.0" in text
    for mark in ("XP-Arc", "DRAGON", "Aboyeur", "Zoran's Law", "SpaZzMatiC"):
        assert mark in text, f"NOTICE is missing trademark reservation for {mark!r}"


def test_pyproject_license_is_apache():
    text = _read("pyproject.toml")
    assert 'license = {text = "Apache-2.0"}' in text
    assert "License :: OSI Approved :: Apache Software License" in text
    _assert_no_live_mit_or_bsl(text, "pyproject.toml")


def test_constitution_asserts_apache():
    text = _read("CONSTITUTION.MD")
    assert "Version 1.6 | Apache License 2.0" in text
    assert "Apache License, Version 2.0" in text
    # Section 11.2 must not still say MIT/BSL is the live license.
    section_112 = text.split("### Section 11.2", 1)[1].split("---", 1)[0]
    _assert_no_live_mit_or_bsl(section_112, "CONSTITUTION.MD Section 11.2")
    quick_ref = text.split("APPENDIX B", 1)[1]
    _assert_no_live_mit_or_bsl(quick_ref, "CONSTITUTION.MD Appendix B quick reference")


def test_legal_md_asserts_apache():
    text = _read("LEGAL.md")
    license_section = text.split("## License", 1)[1]
    assert "Apache License, Version 2.0" in license_section
    _assert_no_live_mit_or_bsl(license_section, "LEGAL.md License section")


def test_whitepaper_asserts_apache():
    text = _read("WHITEPAPER.md")
    header = text.split("---", 1)[0]
    assert "Apache License 2.0" in header
    section_9 = text.split("## Section 9", 1)[1].split("## Section 10", 1)[0]
    normalized = " ".join(section_9.split())
    assert "Apache License, Version 2.0" in normalized
    _assert_no_live_mit_or_bsl(section_9, "WHITEPAPER.md Section 9")


def test_whitepaper_has_relicense_changelog_entry():
    text = _read("WHITEPAPER.md")
    assert "Changelog: Relicense to Apache 2.0" in text


def test_readme_asserts_apache():
    text = _read("README.md")
    license_section = text.split("## License", 1)[1]
    assert "Apache License, Version 2.0" in license_section
    _assert_no_live_mit_or_bsl(license_section, "README.md License section")


def test_architecture_version_matrix_apache():
    text = _read("ARCHITECTURE.md")
    version_matrix = text.split("## 6. Version Matrix", 1)[1]
    assert "Apache-2.0" in version_matrix


def test_gauntlet_constitution_asserts_apache():
    text = _read("Gauntlet_CONSTITUTION.md")
    assert "**License:** Apache License 2.0" in text
    _assert_no_live_mit_or_bsl(text, "Gauntlet_CONSTITUTION.md")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
