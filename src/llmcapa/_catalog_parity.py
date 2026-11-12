"""Compare the authoritative JSON catalog and SQLite without network access."""

from __future__ import annotations

import json
from collections import defaultdict
from unittest.mock import patch

from ._catalog_db import check_catalog
from ._catalog_index import (
    _BUCKET_LENGTH,
    _decode_lookup_block,
    lookup_names,
    parse_numeric_name,
)
from .registry import ModelNotFoundError, Registry


class CatalogParityError(RuntimeError):
    """The two catalog backends returned different results."""


def _require_equal(label, expected, actual):
    if expected != actual:
        raise CatalogParityError(f"{label}: JSON and SQLite differ")


def _json(cap):
    return json.dumps(cap.to_dict(), sort_keys=True, ensure_ascii=False)


def _compare_capabilities(label, expected, actual):
    if _json(expected) != _json(actual):
        raise CatalogParityError(
            f"{label}: different Capability fields for {expected.model_id!r}"
        )


def _compare_mapping(label, expected, actual, checked):
    rows = list(actual.items())
    _require_equal(f"{label} keys/order", list(expected), [key for key, _ in rows])
    for key, cap in rows:
        original = expected[key]
        pair = (id(original), id(cap))
        if pair not in checked:
            _compare_capabilities(f"{label}/{key}", original, cap)
            checked.add(pair)


def _get(registry, name, provider):
    try:
        return registry._get_local(name, provider)
    except ModelNotFoundError:
        return None


def _compare_query(expected, actual, name, provider):
    left = _get(expected, name, provider)
    right = _get(actual, name, provider)
    label = f"get({name!r}, {provider!r})"
    if left is None or right is None:
        _require_equal(label, left is None, right is None)
    else:
        _compare_capabilities(label, left, right)


def _compare_search(expected, actual, prefix, provider, deprecated, limit):
    left = expected._search_local(prefix, provider, deprecated, limit)
    right = actual._search_local(prefix, provider, deprecated, limit)
    label = f"search({prefix!r}, {provider!r}, {deprecated}, {limit})"
    _require_equal(f"{label} count", len(left), len(right))
    for original, cap in zip(left, right):
        _compare_capabilities(label, original, cap)


def _query_probes(expected, actual):
    """Exercise indexed lookups before the exhaustive comparison decodes data."""
    for provider, models in expected._by_provider.items():
        if not models:
            continue
        keys = list(models)
        for key in dict.fromkeys((keys[0], keys[len(keys) // 2], keys[-1])):
            cap = models[key]
            _compare_query(expected, actual, cap.model_id, provider)
            for alias in (cap.aliases or [])[:2]:
                _compare_query(expected, actual, alias, provider)
            prefix = cap.model_id[:8]
            _compare_search(expected, actual, prefix, provider, True, None)
            _compare_search(expected, actual, prefix, provider, False, 3)
        for cap in models.values():
            parsed = parse_numeric_name(cap.model_id)
            if parsed is not None:
                shape, version = parsed
                newer = ".".join(str(part) for part in (*version, 1))
                name = shape.replace("<version>", newer, 1)
                _compare_query(expected, actual, name, provider)
                break
        _compare_query(expected, actual, "nonexistent-parity-model-xyz", provider)
    for key in ("nonexistent-parity-model-xyz", *list(expected._models)[:3]):
        _compare_query(expected, actual, key, None)
        _compare_search(expected, actual, key[:12], None, True, 5)


def compare_registries(expected, actual):
    """Exhaustively compare both index maps and sample actual query behavior."""
    _require_equal(
        "provider order", list(expected._by_provider), list(actual._by_provider)
    )
    _require_equal(
        "provider files",
        expected._catalog_files_by_provider,
        actual._catalog_files_by_provider,
    )
    index = actual._catalog_index
    if index is None:
        raise CatalogParityError("SQLite backend was not used")
    candidate_ids = index.candidate_ids

    def checked_candidates(kind, term):
        ids = candidate_ids(kind, term)
        if ids is None:
            raise CatalogParityError(
                f"SQLite candidate lookup fell back: {kind}/{term!r}"
            )
        return ids

    with patch.object(index, "candidate_ids", side_effect=checked_candidates) as probe:
        _query_probes(expected, actual)
        if not probe.called:
            raise CatalogParityError("SQLite candidate lookup was not exercised")
    checked = set()
    _compare_mapping("flat", expected._models, actual._models, checked)
    _require_equal("aliases", expected._alias_index, dict(actual._alias_index.items()))
    for provider, models in expected._by_provider.items():
        _compare_mapping(provider, models, actual._by_provider[provider], checked)
    if index._fallback is not None:
        raise CatalogParityError("SQLite backend was not used throughout verification")
    return {
        "providers": len(expected._by_provider),
        "scoped_models": sum(len(m) for m in expected._by_provider.values()),
        "flat_models": len(expected._models),
        "aliases": len(expected._alias_index),
    }


def _verify_postings(expected, index):
    """Check every stored candidate, including aliases and numeric shapes."""
    with index._connect() as conn:
        records = {}
        for provider, key, record_id in conn.execute(
            "SELECT provider, model_key, capability_id FROM models"
        ):
            records[record_id] = expected._by_provider[provider][key]
        for key, record_id in conn.execute(
            "SELECT model_key, capability_id FROM flat_models"
        ):
            records[record_id] = expected._models[key]
        expected_ids = {row[0] for row in conn.execute("SELECT id FROM capabilities")}
        _require_equal("capability record IDs", expected_ids, set(records))
        buckets = defaultdict(set)
        for record_id, cap in records.items():
            for kind, name, shape in lookup_names(cap):
                is_alias = kind in ("alias", "alias_exact")
                buckets["name", name[:_BUCKET_LENGTH]].add((name, record_id, is_alias))
                if shape is not None:
                    buckets["shape", shape[:_BUCKET_LENGTH]].add(
                        (shape, record_id, False)
                    )
        previous = None
        observed = set()
        count = 0
        for kind, bucket, payload in conn.execute(
            "SELECT kind, bucket, payload FROM lookup_blocks "
            "ORDER BY kind, bucket, ordinal"
        ):
            key = (kind, bucket)
            if key != previous:
                if previous is not None:
                    _require_equal(
                        f"lookup bucket {previous}",
                        buckets.pop(previous, set()),
                        observed,
                    )
                    count += len(observed)
                previous = key
                observed = set()
            observed.update(_decode_lookup_block(payload))
        if previous is not None:
            _require_equal(
                f"lookup bucket {previous}", buckets.pop(previous, set()), observed
            )
            count += len(observed)
        _require_equal("missing lookup buckets", {}, dict(buckets))
        return count


def verify_catalog():
    """Validate the bundled snapshot against JSON, ignoring user caches."""
    expected = Registry()
    expected._load_bundled_files()
    expected._loaded = True
    actual = Registry()
    if not actual._try_load_sqlite():
        raise CatalogParityError("Cannot open bundled SQLite catalog")
    actual._loaded = True
    check_catalog(actual._catalog_index.database)
    counts = compare_registries(expected, actual)
    counts["lookup_postings"] = _verify_postings(expected, actual._catalog_index)
    return counts
