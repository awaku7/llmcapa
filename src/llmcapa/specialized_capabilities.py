"""Normalized capability records for document, embedding, ranking, and spatial models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar


class _TupleCapability:
    """Small shared serializer for tuple-valued capability metadata."""

    _tuple_fields: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def _from_dict_values(cls, data: dict[str, Any]) -> dict[str, Any]:
        values = dict(data)
        for key in cls._tuple_fields:
            values[key] = tuple(values.get(key) or ())
        return values

    def _to_dict_values(self) -> dict[str, Any]:
        result = asdict(self)
        for key in self._tuple_fields:
            result[key] = list(getattr(self, key))
        return result


@dataclass(frozen=True)
class DocumentCapability(_TupleCapability):
    """Detailed file/document input and extraction metadata."""

    accepts_file: bool | None = None
    accepts_url: bool | None = None
    accepts_file_id: bool | None = None
    input_formats: tuple[str, ...] = ()
    input_mime_types: tuple[str, ...] = ()
    max_input_bytes: int | None = None
    max_pages: int | None = None
    max_file_count: int | None = None
    ocr: bool | None = None
    table_extraction: bool | None = None
    layout_analysis: bool | None = None
    structured_extraction: bool | None = None
    citations: bool | None = None
    output_formats: tuple[str, ...] = ()
    output_mime_types: tuple[str, ...] = ()
    source_url: str | None = None
    checked_at: str | None = None
    status: str = "documented"
    extra: dict[str, Any] = field(default_factory=dict)

    _tuple_fields: ClassVar[tuple[str, ...]] = (
        "input_formats",
        "input_mime_types",
        "output_formats",
        "output_mime_types",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentCapability:
        return cls(**cls._from_dict_values(data))

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict_values()


@dataclass(frozen=True)
class EmbeddingCapability(_TupleCapability):
    """Detailed vector embedding output metadata."""

    embedding: bool | None = None
    dimensions: int | None = None
    dimensions_values: tuple[int, ...] = ()
    max_input_items: int | None = None
    max_input_tokens: int | None = None
    output_formats: tuple[str, ...] = ()
    precision_values: tuple[str, ...] = ()
    normalized: bool | None = None
    distance_metrics: tuple[str, ...] = ()
    truncation_values: tuple[str, ...] = ()
    language_values: tuple[str, ...] = ()
    source_url: str | None = None
    checked_at: str | None = None
    status: str = "documented"
    extra: dict[str, Any] = field(default_factory=dict)

    _tuple_fields: ClassVar[tuple[str, ...]] = (
        "dimensions_values",
        "output_formats",
        "precision_values",
        "distance_metrics",
        "truncation_values",
        "language_values",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingCapability:
        return cls(**cls._from_dict_values(data))

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict_values()


@dataclass(frozen=True)
class RerankCapability(_TupleCapability):
    """Detailed document reranking metadata."""

    rerank: bool | None = None
    max_documents: int | None = None
    max_query_chars: int | None = None
    top_n_max: int | None = None
    returns_scores: bool | None = None
    returns_documents: bool | None = None
    score_range: tuple[float, ...] = ()
    truncation_values: tuple[str, ...] = ()
    language_values: tuple[str, ...] = ()
    source_url: str | None = None
    checked_at: str | None = None
    status: str = "documented"
    extra: dict[str, Any] = field(default_factory=dict)

    _tuple_fields: ClassVar[tuple[str, ...]] = (
        "score_range",
        "truncation_values",
        "language_values",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RerankCapability:
        return cls(**cls._from_dict_values(data))

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict_values()


@dataclass(frozen=True)
class SpatialCapability(_TupleCapability):
    """3D, geospatial, and spatial-media metadata."""

    spatial: bool | None = None
    kind_values: tuple[str, ...] = ()
    input_formats: tuple[str, ...] = ()
    input_mime_types: tuple[str, ...] = ()
    output_formats: tuple[str, ...] = ()
    output_mime_types: tuple[str, ...] = ()
    coordinate_systems: tuple[str, ...] = ()
    dimensions: tuple[int, ...] = ()
    supports_3d: bool | None = None
    supports_mesh: bool | None = None
    supports_point_cloud: bool | None = None
    supports_geospatial: bool | None = None
    source_url: str | None = None
    checked_at: str | None = None
    status: str = "documented"
    extra: dict[str, Any] = field(default_factory=dict)

    _tuple_fields: ClassVar[tuple[str, ...]] = (
        "kind_values",
        "input_formats",
        "input_mime_types",
        "output_formats",
        "output_mime_types",
        "coordinate_systems",
        "dimensions",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpatialCapability:
        return cls(**cls._from_dict_values(data))

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict_values()
