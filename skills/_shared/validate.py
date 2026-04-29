"""
Shared schema validation helper for QA-Skills.
Usage:
    from validate import validate_or_warn
    ok, errors = validate_or_warn(data, "analysis")
    if not ok:
        print(f"Validation failed: {errors}")
"""
import json
import os
from typing import Tuple, List

SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "schemas")

def load_schema(schema_name: str) -> dict:
    path = os.path.join(SCHEMAS_DIR, f"{schema_name}.schema.json")
    with open(path) as f:
        return json.load(f)

def validate_or_warn(data: dict, schema_name: str) -> Tuple[bool, List[str]]:
    """
    Validate data against a named schema.
    Returns (True, []) on success, (False, [error strings]) on failure.
    Does NOT raise — caller decides whether to abort or continue.
    """
    try:
        import jsonschema
        schema = load_schema(schema_name)
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if errors:
            msgs = [f"{'.'.join(str(p) for p in e.path) or 'root'}: {e.message}" for e in errors]
            return False, msgs
        return True, []
    except ImportError:
        # jsonschema not available — skip validation silently
        return True, []
    except Exception as e:
        return False, [f"Schema load error for '{schema_name}': {e}"]


def get_message(key: str, locale: str = "en", **kwargs) -> str:
    """
    Look up a user-facing message by key from the message catalog.
    Falls back to the key itself if not found.
    """
    messages_dir = os.path.join(os.path.dirname(__file__), "messages")
    lang = locale if locale in ("he", "en") else "en"
    path = os.path.join(messages_dir, f"{lang}.json")
    try:
        with open(path) as f:
            catalog = json.load(f)
        template = catalog.get(key, key)
        return template.format(**kwargs) if kwargs else template
    except Exception:
        return key
