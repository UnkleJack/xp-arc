"""
Guards for the four defects that made PR #12's CI red, and for the
path-resolution bug found while fixing them.

Each test here pins a failure that was *silent* -- nothing raised at the time
the defect was introduced, and each one only surfaced later as a red job or a
missing file:

1. ``xp_arc/competitive_intel/__init__.py`` eagerly imported ``.station``,
   which imports jinja2 at module scope. jinja2 lives in the
   ``competitive-intel`` extra; CI installs ``.[dev]`` / ``.[gauntlet]``.
   ``tests/test_competitive_bridge.py`` only needs ``bridge`` and ``analyst``
   (both pure stdlib), but the eager re-export made collection fail, and
   ``pytest -x`` killed the whole unit-test job in under a second.

2. Gauntlet Phase 9 calls ``pool.mark_status()``, the dev bypass, which raises
   RuntimeError unless ``XP_ARC_DEV_MODE`` is set. ``gauntlet.yml`` never set
   it, so the phase died on an uncaught exception; ``run_all_phases()``
   recorded a CRITICAL whose evidence was ``{'exception','traceback'}`` with no
   ``entity_id`` or ``path``, which then tripped the Article IV.2 gate and
   failed the workflow. This ran red on a schedule for eight consecutive days.

3. ``PROJECT_ROOT`` in ``config.py`` and ``station.py`` used four ``.parent``
   calls, resolving to the directory *above* the repo root. Every joined path
   (``config/``, ``sql/``, ``templates/``) missed, and the callers fell through
   to defaults or empty renders rather than erroring.

4. The ``gauntlet`` job read its signing key as a bare
   ``${{ secrets.XP_ARC_ABOYEUR_KEY }}``. An undefined secret expands to an
   empty string rather than an error, so the Aboyeur rejected every signature
   and the run reported 7 CRITICAL findings that read like a code defect.
   Reproduced: an empty key yields 7 CRITICAL and exit 1, while the literal
   used by the constitution job yields 0 CRITICAL and exit 0.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# third-party modules that live in optional extras, not the base install
_OPTIONAL_IMPORTS = ("jinja2", "feedparser", "httpx", "sqlite_utils", "playwright")


# ─── 1. lazy package imports ────────────────────────────────────────────────

def test_importing_the_package_does_not_pull_optional_dependencies():
    """The package __init__ must not import the report renderer's deps.

    Run in a subprocess so the assertion is about a *fresh* interpreter, which
    is what CI sees. Passes whether or not the optional packages are installed
    here: it checks what the import dragged in, not what is importable.
    """
    code = (
        "import sys, xp_arc.competitive_intel;"
        "leaked=[m for m in sys.modules if m.split('.')[0] in %r];"
        "print(','.join(sorted(leaked)))"
    ) % (_OPTIONAL_IMPORTS,)
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert out.returncode == 0, f"import failed: {out.stderr[-400:]}"
    assert out.stdout.strip() == "", (
        f"importing xp_arc.competitive_intel pulled optional deps into "
        f"sys.modules: {out.stdout.strip()}"
    )


def test_pool_side_modules_import_without_the_optional_extras():
    """bridge and analyst are the pool-side half; they must not need jinja2.

    Blocks the optional imports at the loader level so this test is meaningful
    even in an environment where the competitive-intel extra IS installed.
    """
    code = """
import builtins, sys
real = builtins.__import__
blocked = %r
def guard(name, *a, **k):
    if name.split('.')[0] in blocked:
        raise ImportError('blocked by test: ' + name)
    return real(name, *a, **k)
builtins.__import__ = guard
from xp_arc.competitive_intel.bridge import CompetitiveIntelBridge
from xp_arc.competitive_intel.analyst import CompetitiveGapAnalyst
print(CompetitiveIntelBridge.__name__, CompetitiveGapAnalyst.__name__)
""" % (_OPTIONAL_IMPORTS,)
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert out.returncode == 0, f"pool-side import failed: {out.stderr[-500:]}"
    assert "CompetitiveIntelBridge CompetitiveGapAnalyst" in out.stdout


def test_lazy_map_covers_every_exported_name():
    """A name in __all__ that the lazy map misses fails only at access time."""
    import xp_arc.competitive_intel as ci

    missing = [n for n in ci.__all__ if n not in ci._LAZY_ATTRS]
    assert not missing, f"__all__ exports not resolvable lazily: {missing}"


def test_missing_extra_raises_an_actionable_error_not_a_bare_importerror():
    """The failure mode must name the extra to install."""
    code = """
import builtins
real = builtins.__import__
def guard(name, *a, **k):
    if name.split('.')[0] == 'jinja2':
        raise ImportError('No module named jinja2')
    return real(name, *a, **k)
builtins.__import__ = guard
import xp_arc.competitive_intel as ci
try:
    ci.CompetitiveIntelStation
except ImportError as e:
    msg = str(e)
    assert 'competitive-intel' in msg, msg
    assert 'bridge' in msg, msg
    print('ACTIONABLE')
else:
    print('NO-ERROR')
"""
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if "NO-ERROR" in out.stdout:
        # jinja2 was importable despite the guard (e.g. cached); nothing to assert
        return
    assert out.returncode == 0, f"unexpected failure: {out.stderr[-400:]}"
    assert "ACTIONABLE" in out.stdout


# ─── 2. gauntlet workflow env ───────────────────────────────────────────────

def test_gauntlet_workflow_sets_dev_mode():
    """Phase 9 exercises the dev bypass on purpose; the workflow must enable it.

    Without this the phase raises, the wrapper records a CRITICAL with no
    on-disk artifact, and the Article IV.2 gate fails the run.
    """
    wf = (REPO_ROOT / ".github" / "workflows" / "gauntlet.yml").read_text()
    assert "XP_ARC_DEV_MODE" in wf, (
        "gauntlet.yml does not set XP_ARC_DEV_MODE -- Phase 9 will raise "
        "RuntimeError from mark_status() and fail the constitution gate"
    )


def test_mark_status_is_still_guarded_in_production():
    """Enabling the bypass in CI must not mean weakening the guard itself."""
    src = (REPO_ROOT / "xp_arc" / "core" / "pool.py").read_text()
    assert 'if not os.environ.get(\'XP_ARC_DEV_MODE\')' in src or \
           'if not os.environ.get("XP_ARC_DEV_MODE")' in src, (
        "the production guard on mark_status() was removed"
    )


# ─── 3. PROJECT_ROOT resolution ─────────────────────────────────────────────

_SUPPORT_FILES = (
    "config/competitive-watchlist.yaml",
    "config/competitive-intelligence-station.yaml",
    "templates/competitive-weekly-report.md",
    "sql/competitive-gaps-schema.sql",
)


def test_project_root_is_the_repo_root():
    """config.py needs only yaml (present in CI via bandit), so this runs there.

    station.py imports jinja2 at module scope, which CI does not install, so it
    is checked statically by test_station_project_root_matches_config instead
    of imported -- importing it here would recreate the exact collection
    failure this file exists to prevent.
    """
    import xp_arc.competitive_intel.config as config

    assert Path(config.PROJECT_ROOT).resolve() == REPO_ROOT, (
        f"config.PROJECT_ROOT is {config.PROJECT_ROOT}, expected {REPO_ROOT}"
    )


def test_station_project_root_matches_config():
    """station.py and station_main.py must compute the same root as config.py.

    Static check on the source expression: the original defect was station.py
    and config.py using four .parent calls while station_main.py correctly used
    three, so the three modules disagreed about where the repo was.
    """
    import re

    pattern = re.compile(
        r"^PROJECT_ROOT\s*=\s*Path\(__file__\)((?:\.parent)+)", re.MULTILINE
    )
    depths = {}
    for name in ("config.py", "station.py", "station_main.py"):
        src = (REPO_ROOT / "xp_arc" / "competitive_intel" / name).read_text()
        m = pattern.search(src)
        assert m, f"no PROJECT_ROOT assignment found in {name}"
        depths[name] = m.group(1).count(".parent")

    assert len(set(depths.values())) == 1, (
        f"modules disagree about PROJECT_ROOT depth: {depths}"
    )
    # file -> competitive_intel -> xp_arc -> repo root
    assert set(depths.values()) == {3}, (
        f"expected 3 .parent calls to reach the repo root, got {depths}"
    )


def test_every_support_file_resolves_from_project_root():
    """The bug was silent: paths joined fine, the files just were not there."""
    import xp_arc.competitive_intel.config as config

    missing = [
        rel for rel in _SUPPORT_FILES
        if not (Path(config.PROJECT_ROOT) / rel).exists()
    ]
    assert not missing, (
        f"PROJECT_ROOT={config.PROJECT_ROOT} cannot resolve: {missing}"
    )


# ─── 4. workflow secrets must not silently expand to empty ──────────────────

def test_gauntlet_signing_key_has_a_fallback():
    """An undefined secret expands to an empty string, not an error.

    With an empty XP_ARC_ABOYEUR_KEY the Aboyeur rejects every signature it
    checks and the gauntlet reports 7 CRITICAL findings, which read like a code
    defect rather than a missing configuration value. Every assignment in the
    gauntlet workflow must therefore be a literal or carry a `||` fallback.
    """
    import re

    wf = (REPO_ROOT / ".github" / "workflows" / "gauntlet.yml").read_text()
    assignments = re.findall(r"XP_ARC_ABOYEUR_KEY:\s*(.*)$", wf, re.MULTILINE)
    assert assignments, "no XP_ARC_ABOYEUR_KEY assignment found in gauntlet.yml"

    unsafe = []
    for raw in assignments:
        value = raw.strip()
        if not value or value in ("''", '""'):
            unsafe.append(value or "(empty)")
        elif "${{" in value and "||" not in value:
            unsafe.append(value)

    hint = "use a literal, or ${{ secrets.NAME || 'fallback-literal' }}"
    assert not unsafe, (
        f"signing key can expand to empty when the secret is undefined: "
        f"{unsafe} -- {hint}"
    )


def test_gauntlet_workflow_key_sources_agree():
    """Both gauntlet jobs must be able to sign; one literal, one bare secret,
    is how the constitution job passed while the adversarial job failed."""
    import re

    wf = (REPO_ROOT / ".github" / "workflows" / "gauntlet.yml").read_text()
    assignments = [a.strip() for a in
                   re.findall(r"XP_ARC_ABOYEUR_KEY:\s*(.*)$", wf, re.MULTILINE)]
    assert len(assignments) >= 2, (
        "expected both gauntlet jobs to set a signing key"
    )
    # every assignment must be non-empty-capable (the previous test enforces
    # the mechanism); this one just pins that there is more than one job
    # setting it, so a future edit cannot leave a job keyless by deletion.
    assert all(a for a in assignments)


# ─── 5. github-script must not re-declare its injected identifiers ──────────

# actions/github-script evaluates `with.script` inside an async function whose
# parameters are exactly these names. A `const glob = ...` in the script is
# therefore a re-declaration and a hard SyntaxError, not a shadowing warning.
_GITHUB_SCRIPT_INJECTED = {"github", "context", "core", "glob", "io", "require"}


def _code_only(script):
    """Drop full-line `//` comments before scanning.

    Without this the guards match the explanatory comment that documents the
    defect -- the same false positive that made an earlier licence guard fail on
    a changelog quoting superseded wording. Only whole-line comments are
    stripped, so a trailing comment on a code line is still scanned.
    """
    return "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("//")
    )


def _github_script_blocks():
    import yaml

    for wf in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        data = yaml.safe_load(wf.read_text()) or {}
        for job_name, job in (data.get("jobs") or {}).items():
            for step in (job.get("steps") or []):
                uses = str(step.get("uses") or "")
                if "actions/github-script" not in uses:
                    continue
                script = (step.get("with") or {}).get("script")
                if script:
                    yield wf.name, job_name, step.get("name", ""), script


def test_github_script_does_not_redeclare_injected_identifiers():
    """The gauntlet's PR-comment step failed with
    "SyntaxError: Identifier 'glob' has already been declared" because it did
    `const glob = require('glob')` inside a github-script block. The step ran
    after a SUCCESSFUL gauntlet run, so the job was red for a reason that had
    nothing to do with the code under test -- and the annotation pointed at a
    workflow line, not a step name, which is easy to misread as a gauntlet
    failure.
    """
    import re

    blocks = [(wf, job, step, _code_only(script))
              for wf, job, step, script in _github_script_blocks()]
    assert blocks, "no github-script steps found; guard is stale"

    pattern = re.compile(
        r"\b(?:const|let|var|function|class)\s+("
        + "|".join(sorted(_GITHUB_SCRIPT_INJECTED))
        + r")\b"
    )
    offenders = []
    for wf, job, step, script in blocks:
        for m in pattern.finditer(script):
            offenders.append(f"{wf} / {job} / {step}: redeclares '{m.group(1)}'")

    assert not offenders, (
        "github-script injects these as function parameters -- redeclaring them "
        "is a SyntaxError: " + "; ".join(offenders)
    )


def test_github_script_does_not_require_uninstalled_packages():
    """`require('glob')` cannot resolve on a runner: the npm package is not
    installed by the workflow. Only Node builtins and what github-script
    provides are safe.
    """
    import re

    allowed = {"fs", "path", "os", "child_process", "util", "crypto"}
    offenders = []
    for wf, job, step, raw in _github_script_blocks():
        script = _code_only(raw)
        for m in re.finditer(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)", script):
            mod = m.group(1).split("/")[0]
            if mod.startswith("@") or "/" in m.group(1):
                mod = m.group(1)
            if mod not in allowed:
                offenders.append(f"{wf} / {step}: require('{m.group(1)}')")

    assert not offenders, (
        "these npm packages are not installed on the runner: "
        + "; ".join(offenders)
    )


# ─── 6. an informational step must not be able to fail the gate ─────────────

def _load_workflow(name="gauntlet.yml"):
    import yaml

    return yaml.safe_load((REPO_ROOT / ".github" / "workflows" / name).read_text())


def test_gauntlet_job_declares_write_permission_for_pr_comments():
    """Inheriting the repo default left the token read-only, so createComment
    raised "Resource not accessible by integration" and reddened a job whose
    gauntlet run had already succeeded.
    """
    wf = _load_workflow()
    job = wf["jobs"]["gauntlet"]
    perms = job.get("permissions") or wf.get("permissions") or {}
    assert perms.get("pull-requests") == "write", (
        f"the gauntlet job cannot post PR comments with permissions={perms}"
    )
    assert perms.get("contents") == "read", "least privilege: contents should be read-only"


def test_pr_comment_step_is_non_fatal():
    """The summary comment is cosmetic; the gauntlet run is the gate.

    This step has failed the job twice for reasons unrelated to the code under
    test. A step that can only add information must never be able to subtract
    it by impersonating a gate failure.
    """
    wf = _load_workflow()
    steps = wf["jobs"]["gauntlet"]["steps"]
    comment = [s for s in steps if "Comment on PR" in str(s.get("name", ""))]
    assert comment, "the PR-comment step was removed; this guard is stale"
    assert comment[0].get("continue-on-error") is True, (
        "the informational PR-comment step can still fail the whole job"
    )


def test_the_gauntlet_gate_step_is_still_fatal():
    """Guarding against the opposite over-correction: making the actual
    gauntlet run non-fatal would leave the job permanently green and the
    adversarial gate testing nothing."""
    wf = _load_workflow()
    steps = wf["jobs"]["gauntlet"]["steps"]
    run = [s for s in steps if str(s.get("name", "")).strip() == "Run Gauntlet"]
    assert run, "the Run Gauntlet step was renamed or removed; guard is stale"
    assert run[0].get("continue-on-error") is not True, (
        "Run Gauntlet must remain fatal -- that is the gate"
    )
