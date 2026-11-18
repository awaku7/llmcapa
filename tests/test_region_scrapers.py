from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")


def _script_module(name: str):
    sys.path.insert(0, SCRIPTS)
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(SCRIPTS)


YES = "![supported](https://docs.aws.amazon.com/bedrock/latest/userguide/images/icons/icon-yes.png)"
NO = "![not-supported](https://docs.aws.amazon.com/bedrock/latest/userguide/images/icons/icon-no.png)"

AMAZON_MD = f"""
**[Model A](model-card-pub-model-a.md)**

| **Region** | **In-Region (`bedrock-runtime`)** | **Geo (`bedrock-runtime`)** | **Global (`bedrock-runtime`)** |
| --- | --- | --- | --- |
| us-east-1 (N. Virginia) | {YES} | {NO} | {YES} |
| us-gov-west-1 (AWS GovCloud (US-West)) | Legacy (EOL: 2026-09-30) | {NO} | {NO} |
| eu-west-1 (Ireland) | {NO} | {YES} | {NO} |

**[Model B](model-card-pub-model-b.md)**

| **Region** | **In-Region (`bedrock-mantle`)** | **In-Region (`bedrock-runtime`)** | **Geo (`bedrock-runtime`)** | **Global (`bedrock-runtime`)** |
| --- | --- | --- | --- | --- |
| us-east-1 (N. Virginia) | {YES} | {NO} | {NO} | {NO} |
| eu-west-1 (Ireland) | {NO} | {YES} | {NO} | {NO} |

**[Model C](model-card-pub-model-c.md)**

| Region | In-Region | Geo | Global |
| --- | --- | --- | --- |
| ap-northeast-1 (Tokyo) | {NO} | {YES} | {NO} |

**[Model B again](model-card-pub-model-b.md)**

| **Region** | **In-Region (`bedrock-mantle`)** | **In-Region (`bedrock-runtime`)** | **Geo (`bedrock-runtime`)** | **Global (`bedrock-runtime`)** |
| --- | --- | --- | --- | --- |
| ap-south-1 (Mumbai) | {YES} | {YES} | {NO} | {NO} |
"""


def test_amazon_region_tables_parse_supported_cells():
    scraper = _script_module("_scrape_amazon_regions")
    tables = scraper.parse_region_tables(AMAZON_MD)

    model_a = tables["pub-model-a"]
    # The legacy GovCloud cell still counts as available in that Region.
    assert model_a["locations"] == ["us-east-1", "us-gov-west-1"]
    assert model_a["geographic_inference_regions"] == ["eu-west-1"]
    assert model_a["global_inference_regions"] == ["us-east-1"]


def test_amazon_region_tables_union_mantle_and_duplicate_sections():
    scraper = _script_module("_scrape_amazon_regions")
    tables = scraper.parse_region_tables(AMAZON_MD)

    # Mantle-only support still counts as direct availability, and the
    # duplicate section for the same card is merged by union.
    assert tables["pub-model-b"]["locations"] == [
        "us-east-1",
        "eu-west-1",
        "ap-south-1",
    ]
    # Unbolded header variant (used by a few models on the page).
    assert tables["pub-model-c"]["geographic_inference_regions"] == ["ap-northeast-1"]


def test_amazon_region_tables_drop_regions_after_stated_eol():
    import datetime

    scraper = _script_module("_scrape_amazon_regions")
    # Model A's GovCloud cell is "Legacy (EOL: 2026-09-30)": it counts as
    # available up to that date, and not on a refresh after it.
    on_eol = scraper.parse_region_tables(AMAZON_MD, as_of=datetime.date(2026, 9, 30))
    assert on_eol["pub-model-a"]["locations"] == ["us-east-1", "us-gov-west-1"]
    after_eol = scraper.parse_region_tables(AMAZON_MD, as_of=datetime.date(2026, 10, 1))
    assert after_eol["pub-model-a"]["locations"] == ["us-east-1"]


def test_amazon_scraper_keeps_datetime_module_binding():
    # fetch_bedrock_regions() uses datetime.date.fromisoformat; the module
    # binding must stay the datetime module (a class import would shadow
    # it and break the standalone entry point).
    import datetime

    scraper = _script_module("_scrape_amazon_regions")
    assert scraper.datetime is datetime
    assert scraper.datetime.date.fromisoformat("2026-11-18") == datetime.date(
        2026, 11, 18
    )


def test_amazon_base_id_strips_geo_prefixes():
    scraper = _script_module("_scrape_amazon_regions")
    assert scraper._base_id("us.anthropic.claude-v1:0") == "anthropic.claude-v1:0"
    assert scraper._base_id("global.amazon.nova-v1:0") == "amazon.nova-v1:0"
    assert scraper._base_id("amazon.nova-v1:0") == "amazon.nova-v1:0"


VERTEX_HTML = """
<h2 id="google-models" data-text="Google model endpoint locations">Google models</h2>
<h3 id="global" data-text="Global">Global</h3>
<table>
  <thead><tr><th></th><th>Global<br>(global)</th></tr></thead>
  <tbody>
    <tr>
      <td><a href="#">Model A</a><br><code>(model-a)</code></td>
      <td aria-label="Supported" class="compare-yes"></td>
    </tr>
    <tr>
      <td><a href="#">Model B</a><br><code>(model-b)</code></td>
      <td></td>
    </tr>
    <tr>
      <td><a href="#">Model C</a><br><code>(model-c)</code></td>
      <td></td>
    </tr>
  </tbody>
</table>
<h3 id="multi-region" data-text="Multi-region">Multi-region</h3>
<table>
  <thead><tr><th></th><th>United States multi-region (us)</th><th>European Union multi-region (eu)</th></tr></thead>
  <tbody>
    <tr>
      <td><a href="#">Model A</a><br><code>(model-a)</code></td>
      <td aria-label="Supported" class="compare-yes"></td>
      <td></td>
    </tr>
  </tbody>
</table>
<h3 id="united-states" data-text="United States">United States</h3>
<table>
  <thead><tr><th></th><th>Iowa (us-central1)</th><th>Oregon (us-west1)</th></tr></thead>
  <tbody>
    <tr>
      <td><a href="#">Model A</a><br><code>(model-a)</code></td>
      <td aria-label="Supported" class="compare-yes"></td>
      <td></td>
    </tr>
    <tr>
      <td><a href="#">Model B</a><br><code>(model-b)</code></td>
      <td></td>
      <td aria-label="Supported" class="compare-yes"></td>
    </tr>
  </tbody>
</table>
"""


def test_vertex_locations_parse_tables():
    scraper = _script_module("_scrape_vertex_regions")
    models = scraper.parse_locations_html(VERTEX_HTML)

    model_a = models["model-a"]
    assert model_a["global_endpoint"] is True
    assert model_a["multi_regions"] == ["us"]
    assert model_a["locations"] == ["us-central1"]

    model_b = models["model-b"]
    assert model_b["global_endpoint"] is False
    assert model_b["locations"] == ["us-west1"]


def test_vertex_fetch_keeps_explicit_empty_record_for_unsupported_model(
    tmp_path, monkeypatch
):
    scraper = _script_module("_scrape_vertex_regions")
    catalog = tmp_path / "vertex-ai.json"
    catalog.write_text(
        json.dumps(
            {
                "models": [
                    {"model_id": "model-a"},
                    {"model_id": "model-c"},
                    {"model_id": "model-absent"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scraper, "VERTEX_JSON", catalog)
    monkeypatch.setattr(scraper, "_fetch", lambda url: VERTEX_HTML.encode())

    result = scraper.fetch_vertex_regions("2026-11-18")

    # Model C is listed on the page but has no supported endpoint: the
    # explicit empty record lets a refresh clear its stale regions.
    assert result["model-c"]["global_endpoint"] is False
    assert "locations" not in result["model-c"]
    assert result["model-c"]["checked_at"] == "2026-11-18"
    # Models absent from the page stay untouched by the refresh.
    assert "model-absent" not in result
    assert result["model-a"]["global_endpoint"] is True

    postprocess = _script_module("_region_capability_postprocess")
    models = [{"model_id": "model-c", "regions": {"locations": ["stale"]}}]
    assert postprocess.apply_regions(models, result) == 1
    assert models[0]["regions"]["global_endpoint"] is False
    assert "locations" not in models[0]["regions"]


def test_region_postprocess_applies_only_listed_models():
    postprocess = _script_module("_region_capability_postprocess")
    models = [
        {"model_id": "a", "regions": None},
        {"model_id": "b"},
        {"model_id": "c", "regions": {"locations": ["keep-me"]}},
    ]
    scraped = {"a": {"locations": ["us-east-1"]}, "b": {"locations": ["eu-west-1"]}}
    assert postprocess.apply_regions(models, scraped) == 2
    assert models[0]["regions"] == {"locations": ["us-east-1"]}
    assert models[1]["regions"] == {"locations": ["eu-west-1"]}
    assert models[2]["regions"] == {"locations": ["keep-me"]}
