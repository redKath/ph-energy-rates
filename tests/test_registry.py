from ph_energy_data.collectors.registry import build_collectors


def test_registry_lists_every_supported_utility() -> None:
    collectors = build_collectors()
    assert sorted(collectors) == ["beneco", "capelco", "meralco"]
    assert all(collector.utility.id == key for key, collector in collectors.items())
