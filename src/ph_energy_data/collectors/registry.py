import importlib
import pkgutil

import ph_energy_data.collectors as package
from ph_energy_data.collectors.base import Collector

_NOT_COLLECTORS = {"base", "fetcher", "registry"}


def discover_collectors() -> dict[str, Collector]:
    """Every module in this package that exposes a `collector` instance, keyed by utility id."""
    found: dict[str, Collector] = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _NOT_COLLECTORS:
            continue
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")
        collector = module.collector
        found[collector.utility.id] = collector
    return found
