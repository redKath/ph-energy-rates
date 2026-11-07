from ph_energy_data.collectors.base import Collector
from ph_energy_data.collectors.beneco import BenecoCollector
from ph_energy_data.collectors.capelco import CapelcoCollector
from ph_energy_data.collectors.meralco import MeralcoCollector
from ph_energy_data.extraction.docling_ocr import DoclingOcr


def build_collectors() -> dict[str, Collector]:
    """Every supported utility's collector, keyed by utility id."""
    collectors: list[Collector] = [
        BenecoCollector(),
        CapelcoCollector(ocr=DoclingOcr()),
        MeralcoCollector(),
    ]
    return {collector.utility.id: collector for collector in collectors}
