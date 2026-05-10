import pytest

def test_config_public_api_imports():
    from atlas_agent.config import AtlasConfig
    from atlas_agent.config import get_config
    from atlas_agent.config import update_config_value
    from atlas_agent.config import delete_config_value
    from atlas_agent.config import get_raw_config
    from atlas_agent.config import set_raw_value
    from atlas_agent.config import unset_raw_value
    from atlas_agent.config import set_atlas_secret

    assert AtlasConfig is not None
    assert callable(get_config)
    assert callable(update_config_value)
    assert callable(delete_config_value)
    assert callable(get_raw_config)
    assert callable(set_raw_value)
    assert callable(unset_raw_value)
    assert callable(set_atlas_secret)

def test_circular_imports():
    import atlas_agent.config
    import atlas_agent.cli
    import atlas_agent.safety.deadman
    assert True
