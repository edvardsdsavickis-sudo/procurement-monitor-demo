from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from procurement_monitor.models import Tender


class ProcurementConnector(ABC):
    name: str

    @abstractmethod
    def fetch(self, start_date: date, end_date: date) -> list[Tender]:
        """Return notices published during the requested period."""

    def enrich(self, tender: Tender) -> Tender:
        """Enrich a notice using its source page."""
        return tender
