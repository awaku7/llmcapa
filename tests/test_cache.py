import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import llmcapa

def test_supports_cache():
    gpt = llmcapa.get("gpt-4o")
    # First call evaluates and caches
    assert gpt.supports("vision") is True
    # Second call should hit cache
    assert gpt.supports("vision") is True
    # Ensure cache attribute exists
    assert hasattr(gpt, "_supports_cache")
    assert gpt._supports_cache["vision"] is True

    # Check to_dict does not include the cache
    d = gpt.to_dict()
    assert "_supports_cache" not in d
