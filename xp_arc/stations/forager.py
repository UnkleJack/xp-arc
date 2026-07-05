"""
The Forager — Garde Manger.

Raw intelligence acquisition. Seeds → DOM extraction → entity writes.
Fallback: passive pool reader, surfaces unhandled entities for human review.

Whitepaper Section 4.4, Station #1.
"""

import re
import urllib.request
import urllib.parse
import ssl
try:
    import certifi
    _CERTIFI_AVAILABLE = True
except ImportError:
    _CERTIFI_AVAILABLE = False
from ..core.station import StationChef

# ─── Input Sanitization (WHITEPAPER 5.5.2) ───────────────────────────────────
# Defense-in-depth: all untrusted input is validated before use.
# Categories: URL (entity_type=url), domain, email, IP, free-text.

_URL_PATTERN = re.compile(
    r'^(https?)://'                          # scheme
    r'[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'  # optional subdomain
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+'  # domain
    r'(:[0-9]{1,5})?'                        # optional port
    r'(/[^\s]*)?$',                          # optional path
    re.IGNORECASE
)

_DOMAIN_PATTERN = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+$'
)

_MAX_URL_LENGTH = 2048
_MAX_DOMAIN_LENGTH = 253  # RFC 1123


_CONTROL_PATTERN = re.compile(r'[\x00-\x1f\x7f-\x9f]')

def _sanitize_url(value: str) -> str | None:
    """
    Sanitize and validate a URL entity value.

    Defenses:
    - Reject null bytes, control characters anywhere (HTTP smuggling / header injection)
    - Reject unexpected schemes (only http/https permitted)
    - Length cap (2048 chars — prevents memory attacks)
    - URL-decode and re-check for encoded injection attempts
    - Pattern match against a strict URL regex
    - Reject if netloc is empty after parsing

    Returns the sanitized URL or None if the input is invalid.
    """
    if not value or not isinstance(value, str):
        return None

    # Reject control characters BEFORE any stripping — a trailing \n is malformed
    # input, not something to silently clean. This prevents the strip() call
    # from masking embedded injection vectors.
    if _CONTROL_PATTERN.search(value):
        return None

    # Length check
    if len(value) > _MAX_URL_LENGTH:
        return None

    # Now safe to strip whitespace only from the validated ends.
    value = value.strip()

    # Decode URL-encoded sequences — this exposes encoded injection attempts
    # so they can be caught by the control-char regex on the second pass.
    try:
        decoded_value = urllib.parse.unquote(value, errors='strict')
        if decoded_value != value:
            # Reject if URL-decoding produced new control characters
            if _CONTROL_PATTERN.search(decoded_value):
                return None
            value = decoded_value
    except ValueError:
        # errors='strict' raises ValueError on invalid %-sequences
        return None

    # Scheme whitelist
    if not value.lower().startswith(('http://', 'https://')):
        return None

    # Parse and validate structure
    try:
        parsed = urllib.parse.urlparse(value)
        netloc = parsed.netloc.encode('idna').decode('ascii')
        if not netloc:
            return None
    except (UnicodeError, ValueError):
        return None

    # Pattern validation on the reconstructed canonical URL
    canonical = f"{parsed.scheme}://{netloc}{parsed.path}"
    if not _URL_PATTERN.match(canonical):
        return None

    return canonical


def _sanitize_domain(value: str) -> str | None:
    """
    Sanitize and validate a domain entity value.

    Defenses:
    - Null-byte and control-character rejection
    - Length cap (253 chars, RFC 1123)
    - Strict label + TLD pattern
    - No surrounding whitespace
    - No embedded null bytes or newlines
    """
    if not value or not isinstance(value, str):
        return None

    value = value.strip()

    if len(value) > _MAX_DOMAIN_LENGTH:
        return None

    if re.search(r'[\x00-\x09\x0b\x0c\x0e-\x1f\x7f-\x9f]', value):
        return None

    if not _DOMAIN_PATTERN.match(value):
        return None

    return value.lower()


class TheForager(StationChef):
    """
    Scrapes target URLs, extracts domains, writes new entities
    back to the pool. This is the Snowball's ignition switch.
    """

    station_id = "forager"
    name = "The Forager"
    handles_types = ['url']
    sla_seconds = 60

    def __init__(self, pool, max_domains_per_target: int = 5, timeout: int = 8):
        super().__init__(pool)
        self.max_domains_per_target = max_domains_per_target
        self.timeout = timeout

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
            self.log(f"Foraging target DOM: {entity_value}")

            # ─── Sanitize the input URL before use (WHITEPAPER 5.5.2) ───────────
            # This is the primary defense against prompt injection via DOM payload.
            # If sanitization fails, fail the task rather than passing raw input downstream.
            safe_url = _sanitize_url(entity_value)
            if not safe_url:
                self.log(f"  [!] URL sanitization failed — possible injection attempt: {entity_value[:100]}")
                self.pool.add_finding(
                    'high', 'forager',
                    f"URL sanitization rejected: {entity_value[:100]}",
                    "Input did not pass URL validation rules. Request logged for review."
                )
                return {
                    'entity_type': 'url',
                    'entity_value': entity_value,
                    'relationships': [],
                    'confidence': 0.0,
                    'notes': f"Sanitization failed: URL format invalid.",
                }

            extracted_domains = []

            # Configure SSL context (Article IV, 4.3)
            if _CERTIFI_AVAILABLE:
                context = ssl.create_default_context(cafile=certifi.where())
            else:
                context = ssl.create_default_context()

            try:
                req = urllib.request.Request(
                    safe_url,   # ← sanitized, not entity_value
                    headers={'User-Agent': 'Mozilla/5.0 (XP-Arc Forager/0.2)'}
                )
                with urllib.request.urlopen(req, timeout=self.timeout, context=context) as response:
                    html = response.read().decode('utf-8', errors='ignore')

                # Extract domains from links
                all_domains = set(re.findall(r'href="https?://([^/"\']+)', html))

                # Filter: external only, skip self-references
                source_domain = re.findall(r'https?://([^/]+)', safe_url)
                source_domain = source_domain[0] if source_domain else ""

                count = 0
                for d in all_domains:
                    # Sanitize each extracted domain before writing to pool
                    safe_domain = _sanitize_domain(d)
                    if not safe_domain:
                        continue
                    if safe_domain == source_domain or safe_domain.endswith(f".{source_domain}"):
                        continue
                    if count >= self.max_domains_per_target:
                        break

                    new_id = self.pool.add_entity('domain', safe_domain)  # ← sanitized
                    if new_id:
                        self.pool.add_edge(safe_url, 'links_to', safe_domain)  # ← sanitized
                        self.log(f"  + Extracted domain: {safe_domain}")
                        extracted_domains.append(safe_domain)
                        count += 1

                # Extract page title
                title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip()[:200] if title_match else "No title"

                self.log(f"  Foraged {len(extracted_domains)} domains from: {safe_url}")

                return {
                    'entity_type': 'url',
                    'entity_value': safe_url,   # ← canonical sanitized form
                    'relationships': extracted_domains,
                    'confidence': 0.85,
                    'notes': f"Title: {title}. Extracted {len(extracted_domains)} external domains.",
                }

            except Exception as e:
                self.log(f"  Failed to forage {safe_url}: {e}")
                return {
                    'entity_type': 'url',
                    'entity_value': safe_url,
                    'relationships': [],
                    'confidence': 0.2,
                    'notes': f"Forage failed: {str(e)}",
                }
