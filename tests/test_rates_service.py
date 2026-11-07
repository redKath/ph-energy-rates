from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.domain.enums import UtilityType
from ph_energy_data.services.rates import list_utilities
from ph_energy_data.storage.models import Utility


def test_province_wildcards_match_literally(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            Utility(
                id="stub",
                name="Stub",
                type=UtilityType.ELECTRIC_COOPERATIVE,
                psgc_code="0102800000",
            )
        )
        session.commit()
        assert [u.id for u in list_utilities(session, province="01028")] == ["stub"]
        assert list_utilities(session, province="%") == []
        assert list_utilities(session, province="_1028") == []
