"""Unit tests for announcement parsing (no network)."""

from __future__ import annotations

import unittest
from datetime import datetime

from palmeiras_monitor.models import SALE_PHASE_ANNOUNCED, SALE_PHASE_OPEN
from palmeiras_monitor.sources.parsing import (
    build_event_from_post,
    diamond_presale_start,
    extract_match_date,
    extract_teams,
    extract_ticket_url,
)

SAMPLE_TEXT = """Venda de ingressos para final da Libertadores no Uruguai; Avanti terá prioridade

O Palmeiras busca a quarta taça da competição diante do Estudiantes-ARG, no dia 28 de novembro, às 17h,
no Estádio Centenário, em Montevidéu (URU).

CRONOGRAMA DE VENDA SEGUINDO O RATING DO AVANTI

1ª Pré-venda
Início: 06/11/2026 – 10h
– Sócios 5 estrelas (10 a 9 pontos)
– Sócios do Plano Diamante
– Associados do clube de qualquer plano Avanti

2ª Pré-venda
Início: 06/11/2026 – 14h
– Sócios do Plano Platina
"""

SAMPLE_HTML = (
    "<p>O Palmeiras busca a quarta taça da competição diante do Estudiantes-ARG, "
    "no dia 28 de novembro, às 17h.</p>"
    "<p>1ª Pré-venda Início: 06/11/2026 – 10h – Sócios do Plano Diamante</p>"
    '<p><a href="http://libertadores.eleventickets.com">Compre aqui</a></p>'
)


class ParsingTests(unittest.TestCase):
    def test_diamond_presale_start(self) -> None:
        start = diamond_presale_start(SAMPLE_TEXT)
        self.assertEqual(start, datetime(2026, 11, 6, 10, 0))

    def test_extract_teams(self) -> None:
        self.assertEqual(extract_teams(SAMPLE_TEXT), "Palmeiras x Estudiantes-ARG")

    def test_extract_match_date(self) -> None:
        self.assertEqual(
            extract_match_date(SAMPLE_TEXT, datetime(2026, 11, 6, 10, 0)),
            "2026-11-28",
        )

    def test_extract_ticket_url(self) -> None:
        self.assertEqual(
            extract_ticket_url(SAMPLE_HTML, "https://palmeiras.com.br/noticias/x/"),
            "http://libertadores.eleventickets.com",
        )

    def test_build_event_from_post(self) -> None:
        post = {
            "title": {"rendered": "Venda de ingressos para final da Libertadores"},
            "link": "https://palmeiras.com.br/noticias/x/",
            "content": {"rendered": SAMPLE_HTML},
        }
        event = build_event_from_post(post, "palmeiras")
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.match, "Palmeiras x Estudiantes-ARG")
        self.assertEqual(event.match_date, "2026-11-28")
        self.assertEqual(event.sale_start_at, "2026-11-06T10:00")
        self.assertEqual(event.sale_phase, SALE_PHASE_ANNOUNCED)
        self.assertEqual(event.official_url, "http://libertadores.eleventickets.com")

    def test_open_marker(self) -> None:
        html = SAMPLE_HTML.replace("Plano Diamante", "Plano Diamante (vendas abertas)")
        post = {
            "title": {"rendered": "Ingressos à venda"},
            "link": "https://palmeiras.com.br/noticias/x/",
            "content": {"rendered": html},
        }
        event = build_event_from_post(post, "avanti")
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.sale_phase, SALE_PHASE_OPEN)


if __name__ == "__main__":
    unittest.main()
