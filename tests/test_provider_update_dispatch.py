from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _dispatcher():
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("_update_all_providers")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_each_bundled_catalog_is_dispatchable_or_explicitly_unavailable():
    dispatcher = _dispatcher()
    catalog_names = {
        path.stem for path in (ROOT / "src" / "llmcapa" / "data").glob("*.json")
        if path.name != "__init__.py"
    }
    normalized_names = {
        dispatcher.CATALOG_NAME_ALIASES.get(name, name) for name in catalog_names
    }

    assert normalized_names == (
        set(dispatcher.PROVIDER_SCRIPTS) | set(dispatcher.UNSUPPORTED_CATALOGS)
    )
    assert not (set(dispatcher.PROVIDER_SCRIPTS) & set(dispatcher.UNSUPPORTED_CATALOGS))


def test_all_dispatch_targets_exist_and_are_provider_specific():
    dispatcher = _dispatcher()

    for provider, relative_script in dispatcher.PROVIDER_SCRIPTS.items():
        script = SCRIPTS / relative_script
        assert script.is_file(), (provider, relative_script)
        assert "openrouter_providers" not in script.parts

    for provider, args in dispatcher.PROVIDER_ARGS.items():
        if provider == "huggingface":
            assert dispatcher.PROVIDER_SCRIPTS[provider] == "_scrape_huggingface.py"
            assert args == ["--save"]
        else:
            assert dispatcher.PROVIDER_SCRIPTS[provider] == "_update_hf_official_orgs.py"
            assert args == ["--provider", provider]


def test_catalog_filename_aliases_resolve_to_dispatch_keys():
    dispatcher = _dispatcher()
    assert dispatcher.CATALOG_NAME_ALIASES == {
        "azure_foundry": "azure-foundry",
        "foundry_local": "foundry-local",
        "llama_cpp": "llama-cpp",
    }
    assert dispatcher.PROVIDER_SCRIPTS["azure-foundry"] == "_update_azure_foundry.py"
    assert dispatcher.PROVIDER_SCRIPTS["foundry-local"] == "_update_foundry_local.py"
    assert dispatcher.PROVIDER_SCRIPTS["llama-cpp"] == "provider_updates/llama_cpp.py"


def test_catalogs_without_verified_updaters_are_not_silently_substituted():
    dispatcher = _dispatcher()
    assert dispatcher.UNSUPPORTED_CATALOGS == {
        "vllm": "the available model list is instance-specific; no canonical catalog to refresh",
    }
    assert all("openrouter_providers" not in path for path in dispatcher.PROVIDER_SCRIPTS.values())
    assert dispatcher.PROVIDER_SCRIPTS["openrouter"] == "_update_openrouter.py"


def test_newly_supported_catalogs_have_individual_update_scripts():
    dispatcher = _dispatcher()
    expected = {
        "laya": "_update_laya.py",
        "liquid": "_update_liquid.py",
        "modellix": "_update_modellix.py",
        "modellix_media": "_update_modellix_media.py",
        "perplexity-router": "_update_perplexity_router.py",
        "typesafe": "_update_typesafe.py",
    }
    for provider, script in expected.items():
        assert dispatcher.PROVIDER_SCRIPTS[provider] == script


def test_hf_org_updater_can_be_invoked_for_a_single_provider():
    import ast

    source = (SCRIPTS / "_update_hf_official_orgs.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    arguments = {
        node.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.arg)
    }
    assert "provider" in arguments or '"--provider"' in source
    assert 'selected = {args.provider: ORGS[args.provider]} if args.provider else ORGS' in source


def test_dispatcher_does_not_schedule_global_postprocessors():
    source = (SCRIPTS / "_update_all_providers.py").read_text(encoding="utf-8")
    assert "_run_capability_postprocessors" not in source
    assert "_image_capability_postprocess.py" not in source
    assert "_preserve_capabilities" not in source
    assert "_read_catalogs" not in source
    assert "_write_catalog" not in source
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source


def test_provider_update_logs_interpolate_dynamic_fields():
    placeholder_pattern = re.compile(
        r'^\s*\+\s*"[^"\n]*\\n## .*audit[^"\n]*\{(?:datetime|SOURCE|n|DOCUMENTED)',
        re.MULTILINE,
    )
    broken = []
    for script in (SCRIPTS / "provider_updates").glob("*.py"):
        source = script.read_text(encoding="utf-8")
        if placeholder_pattern.search(source):
            broken.append(script.name)
    assert not broken, f"non-interpolated log templates: {broken}"


def test_all_29_previously_metadata_only_catalogs_have_inventory_updaters():
    dispatcher = _dispatcher()
    hf_updater = importlib.util.spec_from_file_location(
        "test_hf_inventory_updater", SCRIPTS / "_update_hf_official_orgs.py"
    )
    assert hf_updater and hf_updater.loader
    hf_module = importlib.util.module_from_spec(hf_updater)
    hf_updater.loader.exec_module(hf_module)
    hf_publishers = set(hf_module.ORGS)
    provider_level = {
        "ai21": "provider_updates/ai21.py",
        "bytedance-seed": "provider_updates/bytedance-seed.py",
        "huggingface": "_scrape_huggingface.py",
        "llama-cpp": "provider_updates/llama_cpp.py",
        "lmstudio": "provider_updates/lmstudio.py",
        "morph": "provider_updates/morph.py",
        "perplexity": "provider_updates/perplexity.py",
        "poolside": "provider_updates/poolside.py",
        "relace": "provider_updates/relace.py",
        "sakana": "provider_updates/sakana.py",
        "thinkingmachines": "provider_updates/thinkingmachines.py",
        "writer": "provider_updates/writer.py",
        "z-ai": "provider_updates/z-ai.py",
    }
    assert len(hf_publishers) == 16
    assert len(provider_level) == 13
    assert len(hf_publishers) + len(provider_level) == 29
    assert all(dispatcher.PROVIDER_SCRIPTS[name] == "_update_hf_official_orgs.py" for name in hf_publishers)
    assert all(dispatcher.PROVIDER_SCRIPTS[name] == script for name, script in provider_level.items())
