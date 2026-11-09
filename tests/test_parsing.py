"""Unit tests for announcement parsing (no network)."""

from __future__ import annotations

import unittest
from datetime import datetime

from palmeiras_monitor.models import SALE_PHASE_ANNOUNCED, SALE_PHASE_OPEN
from palmeiras_monitor.sources.parsing import (
    build_event_from_post,
    classify_venue,
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

    def test_venue_home(self) -> None:
        text = (
            "Os ingressos para o jogo contra o Remo, que ocorrerá na quinta-feira (05), "
            "às 19h30, no Nubank Parque, pela 34ª rodada."
        )
        self.assertEqual(classify_venue(text), ("home", "Nubank Parque"))

    def test_venue_away(self) -> None:
        text = (
            "O primeiro duelo com o Fluminense ocorrerá no dia 14 de outubro, "
            "às 21h30, no Maracanã, no Rio de Janeiro (RJ)."
        )
        self.assertEqual(classify_venue(text), ("away", "Maracanã"))

    def test_venue_neutral(self) -> None:
        text = (
            "A final da Libertadores será no dia 28 de novembro, às 17h, "
            "no Estádio Centenário, em Montevidéu (URU)."
        )
        self.assertEqual(classify_venue(text), ("neutral", "Estádio Centenário"))

    def test_venue_away_ignores_later_home_reference(self) -> None:
        text = (
            "O primeiro duelo com o River Plate-ARG, que ocorrerá no dia 17 de setembro, "
            "às 21h30, no Monumental de Núñez, em Buenos Aires (ARG). A comercialização "
            "segue o mesmo formato das pré-vendas realizadas no Allianz Parque – ou seja, "
            "inicialmente estarão aptos os sócios com maior rating."
        )
        self.assertEqual(classify_venue(text), ("away", "Monumental de Núñez"))

    def test_venue_unknown(self) -> None:
        self.assertEqual(classify_venue("Venda de ingressos para o jogo."), ("unknown", None))

    def test_event_carries_venue(self) -> None:
        post = {
            "title": {"rendered": "Ingressos para jogo contra Remo no Nubank Parque"},
            "link": "https://palmeiras.com.br/noticias/remo/",
            "content": {
                "rendered": (
                    "<p>O jogo contra o Remo será no Nubank Parque.</p>"
                    "<p>1ª Pré-venda Início: 29/10/2099 – 12h – Sócios do Plano Diamante</p>"
                )
            },
        }
        event = build_event_from_post(post, "palmeiras")
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.venue_type, "home")
        self.assertEqual(event.venue, "Nubank Parque")
        self.assertEqual(event.announcement_url, "https://palmeiras.com.br/noticias/remo/")


if __name__ == "__main__":
    unittest.main()
