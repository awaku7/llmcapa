"""Normalized capability records for document, embedding, ranking, spatial, and decision models."""

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
@dataclass(frozen=True)
class DecisionCapability(_TupleCapability):
    """Typed-decision output metadata for System One style models.

    A decision model does not generate text. It evaluates typed questions
    against a state and returns typed answers with calibrated probabilities,
    so ``free_form_text`` is ``False`` and ``type_errors_possible`` is
    ``False`` rather than unknown.
    """

    decision: bool | None = None
    question_kinds: tuple[str, ...] = ()
    answer_fields: tuple[str, ...] = ()
    returns_probabilities: bool | None = None
    returns_confidence: bool | None = None
    calibrated_confidence: bool | None = None
    parallel_questions: bool | None = None
    free_form_text: bool | None = None
    type_errors_possible: bool | None = None
    deterministic: bool | None = None
    state_shapes: tuple[str, ...] = ()
    max_state_tokens: int | None = None
    max_total_tokens: int | None = None
    output_token_billing: bool | None = None
    max_questions: int | None = None
    cardinality_max: int | None = None
    rate_limit_tokens_per_second: int | None = None
    rate_limit_requests_per_minute: int | None = None
    language_values: tuple[str, ...] = ()
    endpoints: tuple[str, ...] = ()
    source_url: str | None = None
    checked_at: str | None = None
    status: str = "documented"
    extra: dict[str, Any] = field(default_factory=dict)

    _tuple_fields: ClassVar[tuple[str, ...]] = (
        "question_kinds",
        "answer_fields",
        "state_shapes",
        "language_values",
        "endpoints",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionCapability:
        return cls(**cls._from_dict_values(data))

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict_values()
