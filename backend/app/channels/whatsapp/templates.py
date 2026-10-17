"""WhatsApp Utility Template loader and builders (spec/07 §7.2, content/whatsapp_templates.yaml).

Handles:
- Template definitions loading from content/whatsapp_templates.yaml
- Approval status checking (`approved: true`)
- Formatting Meta Cloud API template components with positional {{1}}, {{2}} parameters
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("abhyas.channels.whatsapp.templates")

_TEMPLATE_FILE = Path(__file__).resolve().parents[4] / "content" / "whatsapp_templates.yaml"

_cached_templates: dict[str, dict[str, Any]] = {}
_loaded: bool = False


def load_whatsapp_templates() -> dict[str, dict[str, Any]]:
    """Loads and caches templates defined in content/whatsapp_templates.yaml."""
    global _cached_templates, _loaded
    if _loaded and _cached_templates:
        return _cached_templates

    templates_by_name: dict[str, dict[str, Any]] = {}
    if not _TEMPLATE_FILE.exists():
        logger.warning("WhatsApp templates file not found: %s", _TEMPLATE_FILE)
        return templates_by_name

    try:
        content = _TEMPLATE_FILE.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
        template_list = data.get("templates", [])
        for tpl in template_list:
            if isinstance(tpl, dict) and "name" in tpl:
                templates_by_name[tpl["name"]] = tpl
                if "key" in tpl:
                    templates_by_name[tpl["key"]] = tpl
        _cached_templates = templates_by_name
        _loaded = True
    except Exception as exc:
        logger.error("Failed to load WhatsApp templates: %s", exc)

    return _cached_templates


def get_template_by_name(name_or_key: str) -> dict[str, Any] | None:
    """Returns template definition by name or catalog key."""
    templates = load_whatsapp_templates()
    return templates.get(name_or_key)


def is_template_approved(name_or_key: str) -> bool:
    """Checks whether a template is marked as approved: true in the catalog."""
    tpl = get_template_by_name(name_or_key)
    if not tpl:
        return False
    return bool(tpl.get("approved", False))


def build_template_components(parameters: list[str]) -> list[dict[str, Any]]:
    """Builds the Meta template 'components' structure for body parameters."""
    if not parameters:
        return []
    return [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in parameters],
        }
    ]


def build_template_payload(
    template_name: str,
    parameters: list[str] | None = None,
    language_code: str = "hi",
) -> dict[str, Any]:
    """Builds complete Meta Graph API template object."""
    components = build_template_components(parameters or [])
    payload: dict[str, Any] = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if components:
        payload["components"] = components
    return payload
