"""Regenerate the large Python AST timing fixtures."""

from pathlib import Path


OUTPUT = Path(__file__).parent / "performance_fixtures"


def _standard_block(index: int) -> list[str]:
    return [
        f"def normalize_record_{index:03}(payload):",
        "    if not isinstance(payload, dict):",
        "        raise ValueError('record must be a mapping')",
        "    normalized = {}",
        "    for key, value in payload.items():",
        "        if key.startswith('_'):",
        "            continue",
        "        if isinstance(value, str):",
        "            normalized[key] = value.strip()",
        "        elif isinstance(value, (int, float, bool)) or value is None:",
        "            normalized[key] = value",
        "        else:",
        "            normalized[key] = str(value)",
        f"    normalized.setdefault('id', 'record-{index:03}')",
        "    return normalized",
        "",
    ]


def _ai_resource(index: int) -> list[str]:
    name = f"item_{index:03}"
    return [
        f"def create_{name}(payload, store, logger):",
        "    if not isinstance(payload, dict):",
        "        raise ValueError('payload must be a dictionary')",
        "    cleaned = {}",
        "    for key, value in payload.items():",
        "        if key.startswith('_'):",
        "            continue",
        "        if isinstance(value, str):",
        "            cleaned[key] = value.strip()",
        "        else:",
        "            cleaned[key] = value",
        "    if 'name' not in cleaned:",
        "        raise ValueError('name is required')",
        "    if 'quantity' in cleaned and cleaned['quantity'] < 0:",
        "        raise ValueError('quantity must be non-negative')",
        "    cleaned.setdefault('status', 'active')",
        f"    cleaned.setdefault('resource_type', '{name}')",
        f"    store['{name}'] = cleaned",
        f"    logger.info('created {name}')",
        "    return cleaned",
        "",
        f"def get_{name}(item_id, store, logger):",
        f"    records = store.get('{name}', {{}})",
        "    if item_id not in records:",
        "        logger.warning('requested record was not found')",
        "        return None",
        "    record = records[item_id]",
        "    if not isinstance(record, dict):",
        "        return None",
        "    return dict(record)",
        "",
        f"def update_{name}(item_id, changes, store, logger):",
        f"    records = store.setdefault('{name}', {{}})",
        "    if item_id not in records:",
        "        raise KeyError(item_id)",
        "    updated = dict(records[item_id])",
        "    for key, value in changes.items():",
        "        if key.startswith('_'):",
        "            continue",
        "        if value is not None:",
        "            updated[key] = value.strip() if isinstance(value, str) else value",
        "    if updated.get('quantity', 0) < 0:",
        "        raise ValueError('quantity must be non-negative')",
        "    records[item_id] = updated",
        f"    logger.info('updated {name}')",
        "    return updated",
        "",
        f"def delete_{name}(item_id, store, logger):",
        f"    records = store.get('{name}', {{}})",
        "    if item_id not in records:",
        "        return False",
        "    del records[item_id]",
        f"    logger.info('deleted {name}')",
        "    return True",
        "",
    ]


def main() -> None:
    standard = [
        '"""Conventional record normalization helpers used for AST timing."""',
        "from collections.abc import Mapping",
        "",
    ]
    for index in range(250):
        standard.extend(_standard_block(index))
    (OUTPUT / "standard_service_4k.py").write_text("\n".join(standard), encoding="utf-8")

    ai_style = [
        '"""',
        "Prompt: Build a Python inventory service with CRUD helpers, input validation,",
        "logging, defaults, and safe handling for each resource in a catalog.",
        "This intentionally repetitive file models verbose code from a simple prompt.",
        '"""',
        "",
    ]
    for index in range(400):
        ai_style.extend(_ai_resource(index))
    (OUTPUT / "ai_generated_service_22k.py").write_text(
        "\n".join(ai_style), encoding="utf-8"
    )

    for filename in ("standard_service_4k.py", "ai_generated_service_22k.py"):
        source = (OUTPUT / filename).read_text(encoding="utf-8")
        print(f"{filename}: {len(source.splitlines()):,} lines, {len(source):,} characters")


if __name__ == "__main__":
    main()
