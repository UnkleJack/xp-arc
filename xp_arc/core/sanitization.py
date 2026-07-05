"""
Output Sanitization — DRAGON layer defense.

WHITEPAPER 5.5.5: Entity values written to graph output (D2) must be sanitized
before rendering. Crafted entity values can produce malformed graph syntax,
break edge parsing, or inject labels that corrupt the graph structure.

Defense-in-depth strategy:
1. Node IDs: strict alphanumeric + underscore + hyphen. All other chars escaped.
2. Edge labels: similar to node IDs but allows more punctuation (relationships).
3. Markdown output: escape backticks, pipes, brackets to prevent injection.
4. All sanitization is lossy (round-trip not required — these are display values).

Every caller that writes entity data to an output format MUST sanitize first.
"""

import re
from typing import Literal

# ─── D2 Graph Sanitization ───────────────────────────────────────────────────

# D2 node IDs: alphanumeric, underscores, hyphens only.
# D2 is very strict about what can appear in a node identifier.
# Reference: https://terrastruct.com/D2.pdf
_D2_NODE_ID_INVALID = re.compile(r'[^\w\-]')
# D2 edge labels: alphanumeric, spaces, underscores, hyphens, punctuation.
# Reject control chars, pipe (|), bracket (<>) which are D2 syntax characters.
_D2_LABEL_INVALID = re.compile(r'[\x00-\x1f\x7f-\x9f|<>]')
# Consecutive underscores in IDs can clash with internal naming conventions.
_MULTI_UNDERSCORE = re.compile(r'_+')


def sanitize_d2_node_id(value: str, max_len: int = 128) -> str:
    """
    Sanitize a string for use as a D2 node identifier.

    Rules:
    - Alphanumeric, underscore, hyphen only.
    - Lowercased (D2 IDs are case-sensitive; canonical form avoids collisions).
    - Truncated to max_len characters.
    - Consecutive underscores collapsed to a single underscore.
    - Empty string returns "unnamed_node" (D2 requires non-empty IDs).
    - All other characters replaced with underscores.

    Example: "GitHub: api.github.com" → "github_api_github_com"
    """
    if not value:
        return "unnamed_node"

    # Truncate before processing to limit work on pathological input.
    value = str(value)[:max_len]

    # Lowercase and replace invalid chars.
    sanitized = _D2_NODE_ID_INVALID.sub('_', value.lower())

    # Collapse consecutive underscores.
    sanitized = _MULTI_UNDERSCORE.sub('_', sanitized)

    # Strip leading/trailing underscores and hyphens from the result.
    sanitized = sanitized.strip('_-')

    if not sanitized:
        return "unnamed_node"

    return sanitized


def sanitize_d2_edge_label(value: str, max_len: int = 256) -> str:
    """
    Sanitize a string for use as a D2 edge label (the relationship name).

    Rules:
    - Control characters rejected.
    - D2 syntax characters (< > |) rejected.
    - Replaced with underscores.
    - Collapsed consecutive underscores.
    - Trimmed to max_len.

    Example: "has <admin> | root access" → "has__admin____root_access"
    """
    if not value:
        return "related"

    value = str(value)[:max_len]

    # Replace D2 syntax chars and control chars with underscore.
    sanitized = _D2_LABEL_INVALID.sub('_', value)

    # Collapse consecutive underscores.
    sanitized = _MULTI_UNDERSCORE.sub('_', sanitized)

    # Strip leading/trailing underscores.
    sanitized = sanitized.strip('_')

    if not sanitized:
        return "related"

    return sanitized


def sanitize_d2_value(value: str, max_len: int = 512) -> str:
    """
    Sanitize an arbitrary entity value for safe inclusion in D2 output.

    Use this for comments, tooltips, or multi-line content in D2 graphs.
    Rejects control characters and D2 structural characters.
    Preserves printable ASCII and unicode word characters.
    """
    if not value:
        return ""

    value = str(value)[:max_len]

    # Remove control characters and D2 structural chars.
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f|<>]', '', value)

    return cleaned.strip()


# ─── Markdown / Delivery Sanitization ────────────────────────────────────────

# Characters that break markdown rendering or allow injection.
_MD_INVALID = re.compile(r'[\x00-\x1f\x7f-\x9f]')


def sanitize_markdown(value: str, max_len: int = 2048) -> str:
    """
    Sanitize an entity value for safe rendering in Markdown output.

    Rules:
    - Control characters stripped.
    - Backticks (`) escaped to prevent inline code injection.
    - Pipe (|) escaped to prevent table injection.
    - Angle brackets (< >) escaped to prevent HTML injection.
    - Length capped.
    - Leading/trailing whitespace stripped.

    Example: `` "| code exec |" `` → `` "\\| code exec \\|" ``
    """
    if not value:
        return ""

    value = str(value)[:max_len]

    # Strip control characters.
    value = _MD_INVALID.sub('', value)

    # Escape markdown-injection characters.
    value = value.replace('\\', '\\\\')   # Backslash first — prevents double-escaping.
    value = value.replace('`', '\\`')
    value = value.replace('|', '\\|')
    value = value.replace('<', '\\<')
    value = value.replace('>', '\\>')

    return value.strip()


def entity_to_d2(entity_value: str, entity_type: str = "entity",
                 shape: Literal["", "circle", "square", "diamond", "hexagon", "circle.person"] = "",
                 label: str | None = None) -> str:
    """
    Render an entity as a D2 node declaration.

    Args:
        entity_value: the raw entity value (will be sanitized for node ID).
        entity_type: optional type label for the node (used in D2 label).
        shape: optional D2 shape (circle, square, diamond, etc.).
        label: optional display label. If None, uses entity_value.

    Returns:
        A D2 node declaration string.

    Example:
        entity_to_d2("github.com", "domain", shape="hexagon")
        # → 'github_api_github_com: { shape: hexagon label: "github.com" }'
    """
    node_id = sanitize_d2_node_id(entity_value)
    display_label = sanitize_d2_value(label if label is not None else entity_value)

    parts = [node_id]
    if display_label:
        parts.append(f'label: "{display_label}"')
    if shape:
        parts.append(f'shape: {shape}')
    if entity_type:
        parts.append(f'# {entity_type}')

    return f"{node_id}: {{ " + " ".join(parts) + " }}"


def edge_to_d2(source: str, relationship: str, target: str,
               source_type: str = "", target_type: str = "") -> str:
    """
    Render an edge as a D2 edge declaration.

    Args:
        source: source entity value (sanitized to node ID).
        relationship: edge label (relationship name, sanitized).
        target: target entity value (sanitized to node ID).

    Returns:
        A D2 edge declaration string.

    Example:
        edge_to_d2("github.com", "links_to", "github.com")
        # → 'github_api_github_com -> github_api_github_com: { label: "links_to" }'
    """
    src_id = sanitize_d2_node_id(source)
    tgt_id = sanitize_d2_node_id(target)
    rel_label = sanitize_d2_edge_label(relationship)

    label_part = f'label: "{rel_label}"' if rel_label else ""
    return f"{src_id} -> {tgt_id}: {{ {label_part} }}"