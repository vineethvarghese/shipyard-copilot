#!/usr/bin/env python3
"""Validate a JSON document against a Shipyard contract.

Stdlib only. Supports the JSON-Schema subset the contracts in ../contracts use:
type (including type arrays), enum, const, required, properties,
additionalProperties (false, true or a schema), items, minLength, maxLength,
minimum, maximum, minItems, maxItems and pattern. Other keywords are ignored.

CLI:
    python3 scripts/shipyard_validate.py <contract-stem> <file|->

<contract-stem> is the file name without `.schema.json` (for example
`reviewer-result`). A `@<major>` suffix (`reviewer-result@1`) is accepted and
checked against the contract's x-contract-version.

If the input is not pure JSON, the LAST fenced ```json block in it is
validated (an agent's final message ends with one).

Exit codes: 0 valid, 1 invalid (or no JSON found), 2 usage error.

Library:
    from shipyard_validate import validate, load_contract
    errors = validate(instance, schema)   # -> list[str]; empty means valid
"""

import json
import os
import re
import sys

CONTRACTS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "contracts"))

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool))
    or (isinstance(v, float) and v.is_integer()),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}

_FENCE_RE = re.compile(r"^[ \t]*```[ \t]*json[ \t]*\r?\n(.*?)^[ \t]*```[ \t]*$", re.DOTALL | re.MULTILINE | re.IGNORECASE)


class UsageError(Exception):
    """Bad arguments: unknown contract, unreadable file."""


def _type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _json_equal(a, b):
    """Equality in the JSON sense: true is not 1, 1 equals 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def _key_path(path, key):
    if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", key):
        return "%s.%s" % (path, key)
    return "%s[%s]" % (path, json.dumps(key))


def _validate(value, schema, path, errors):
    if schema is True or schema is None:
        return
    if schema is False:
        errors.append("%s: no value is allowed here" % path)
        return
    if not isinstance(schema, dict):
        return

    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_TYPE_CHECKS.get(t, lambda v: False)(value) for t in types):
            errors.append("%s: expected type %s, got %s" % (path, " | ".join(types), _type_name(value)))
            return  # further checks would only add noise

    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append("%s: must equal %s" % (path, json.dumps(schema["const"])))

    if "enum" in schema:
        allowed = schema["enum"]
        if not any(_json_equal(value, a) for a in allowed):
            errors.append("%s: %s is not one of %s" % (path, json.dumps(value), json.dumps(allowed)))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append("%s: string shorter than minLength %d" % (path, schema["minLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append("%s: string longer than maxLength %d" % (path, schema["maxLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append("%s: does not match pattern %s" % (path, schema["pattern"]))

    if _type_name(value) in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: %s is less than minimum %s" % (path, value, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: %s is greater than maximum %s" % (path, value, schema["maximum"]))

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append("%s: fewer than minItems %d" % (path, schema["minItems"]))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append("%s: more than maxItems %d" % (path, schema["maxItems"]))
        if "items" in schema:
            for i, item in enumerate(value):
                _validate(item, schema["items"], "%s[%d]" % (path, i), errors)

    if isinstance(value, dict):
        props = schema.get("properties", {}) or {}
        for key in schema.get("required", []) or []:
            if key not in value:
                errors.append("%s: missing required property %s" % (path, json.dumps(key)))
        extra = schema.get("additionalProperties", True)
        for key in sorted(value):
            sub = _key_path(path, key)
            if key in props:
                _validate(value[key], props[key], sub, errors)
            elif extra is False:
                errors.append("%s: additional property %s is not allowed" % (path, json.dumps(key)))
            elif isinstance(extra, dict):
                _validate(value[key], extra, sub, errors)


def validate(instance, schema):
    """Return a list of error strings (JSON paths rooted at `$`); empty list means valid."""
    errors = []
    _validate(instance, schema, "$", errors)
    return errors


def contract_path(stem):
    base = stem.split("@", 1)[0]
    if base.endswith(".schema.json"):
        base = base[: -len(".schema.json")]
    return os.path.join(CONTRACTS_DIR, base + ".schema.json")


def load_contract(stem):
    """Load contracts/<stem>.schema.json. `stem@N` also checks the major version."""
    path = contract_path(stem)
    if not os.path.isfile(path):
        available = sorted(f[: -len(".schema.json")] for f in os.listdir(CONTRACTS_DIR) if f.endswith(".schema.json")) \
            if os.path.isdir(CONTRACTS_DIR) else []
        raise UsageError("unknown contract %r; available: %s" % (stem, ", ".join(available) or "none"))
    with open(path, encoding="utf-8") as fh:
        schema = json.load(fh)
    if "@" in stem:
        want = stem.split("@", 1)[1]
        have = str(schema.get("x-contract-version", "")).split(".", 1)[0]
        if want.split(".", 1)[0] != have:
            raise UsageError("contract %s has major version %s, caller asked for %s" % (path, have or "?", want))
    return schema


def extract_json(text):
    """Parse `text` as JSON; if that fails, parse the last fenced ```json block. Raises ValueError."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("input is empty")
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    blocks = _FENCE_RE.findall(text)
    if not blocks:
        raise ValueError("input is not JSON and contains no fenced ```json block")
    try:
        return json.loads(blocks[-1])
    except ValueError as exc:
        raise ValueError("last ```json block does not parse: %s" % exc)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] in ("-h", "--help"):
        sys.stderr.write("usage: shipyard_validate.py <contract-stem> <file|->\n")
        return 2
    stem, source = argv
    try:
        schema = load_contract(stem)
        if source == "-":
            text = sys.stdin.read()
        else:
            if not os.path.isfile(source):
                raise UsageError("no such file: %s" % source)
            with open(source, encoding="utf-8") as fh:
                text = fh.read()
    except UsageError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2
    try:
        instance = extract_json(text)
    except ValueError as exc:
        print("INVALID %s: %s" % (stem, exc))
        return 1
    errors = validate(instance, schema)
    if errors:
        print("INVALID %s (%d error%s):" % (stem, len(errors), "" if len(errors) == 1 else "s"))
        for err in errors:
            print("  " + err)
        return 1
    print("VALID %s" % stem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
