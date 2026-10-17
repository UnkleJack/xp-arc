"""
Version parsing and release classification shared by the fetchers and the digest.

Handles PEP 440 and SemVer-style strings well enough to order releases of one
package and say what kind of step each release was.
"""

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

# Significance order for sorting and headlines (lower = more important).
SIGNIFICANCE = {'major': 0, 'minor': 1, 'pre-release': 2, 'maintenance': 3,
                'patch': 4, 'nightly': 5, 'release': 6}

_PRE_MARKERS = re.compile(r'(a|b|rc|alpha|beta|dev|canary|next|preview|pre)', re.I)


# Pre-release phases in PEP 440 / common SemVer order.
_PHASE_RANK = {'dev': 0, 'a': 1, 'alpha': 1, 'canary': 1, 'next': 1, 'b': 2, 'beta': 2,
               'preview': 3, 'pre': 3, 'c': 3, 'rc': 3}


@dataclass(frozen=True)
class Version:
    release: Tuple[int, ...]
    is_pre: bool
    pre: Tuple[int, int] = (0, 0)   # (phase rank, number) for pre-releases
    post: int = 0

    def _key(self):
        # Pre-releases sort before the final release; post-releases after it.
        return (self.release, not self.is_pre, self.pre, self.post)

    def __lt__(self, other: 'Version') -> bool:
        return self._key() < other._key()


def parse_version(text: str) -> Optional[Version]:
    """Parse PEP 440 and SemVer-style versions well enough to compare them.

    Returns None for anything without a leading numeric release segment.
    """
    if not text:
        return None
    text = text.strip().lstrip('vV')
    match = re.match(r'^(\d+(?:\.\d+)*)(.*)$', text)
    if not match:
        return None
    release = tuple(int(p) for p in match.group(1).split('.'))
    release = release + (0,) * (3 - len(release)) if len(release) < 3 else release
    suffix = match.group(2)

    post = re.match(r'^[.-]?post(\d*)$', suffix, re.I)
    if post:
        return Version(release, False, post=int(post.group(1) or 0))
    if not suffix:
        return Version(release, False)

    phase = _PRE_MARKERS.search(suffix)
    number = re.search(r'(\d+)', suffix)
    pre = (_PHASE_RANK.get(phase.group(1).lower(), 3) if phase else 3,
           int(number.group(1)) if number else 0)
    return Version(release, True, pre=pre)


def classify(version: Version, previous: Optional[Version], newest_final: Version) -> str:
    """Label one release against its predecessor in version order.

    newest_final is the highest non-pre-release version known for the package.
    A pre-release of a new major does not make the current line "maintenance".
    """
    if previous is None:
        return 'release'
    if version.release[0] < newest_final.release[0]:
        return 'maintenance'
    if version.is_pre:
        # .devN builds (often date-stamped nightlies) are routine, not news.
        return 'nightly' if version.pre[0] == 0 else 'pre-release'
    if version.release[0] != previous.release[0]:
        return 'major'
    if version.release[1] != previous.release[1]:
        return 'minor'
    return 'patch'


def predecessor(version_text: str, all_versions: Iterable[str]) -> Optional[str]:
    """The next-lower version of the same package, by version order."""
    target = parse_version(version_text)
    if target is None:
        return None
    lower = [(parse_version(v), v) for v in all_versions if v != version_text]
    lower = [(p, v) for p, v in lower if p is not None and p < target]
    return max(lower, key=lambda pv: pv[0])[1] if lower else None
