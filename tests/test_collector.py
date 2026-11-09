"""Tests for collector dedupe, fallback alerts, and bootstrap behavior."""

from __future__ import annotations

import logging
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from palmeiras_monitor.collector import Collector
from palmeiras_monitor.sources.store import StoreStatus
from palmeiras_monitor.storage import Storage

PARSED_HTML = (
    "<p>Os ingressos para o jogo contra o Remo serão no Nubank Parque.</p>"
    "<p>1ª Pré-venda Início: 29/10/2099 – 12h – Sócios do Plano Diamante</p>"
)
UNPARSED_HTML = (
    "<p>Os ingressos para o jogo contra o Fluminense serão no Nubank Parque.</p>"
    "<p>Venda a partir de terça, às 12h, no site oficial.</p>"
)


def post(slug: str, title: str, html: str) -> dict:
    return {
        "id": slug,
        "date": "2026-10-28T16:47:07",
        "modified": "2026-10-28T16:47:07",
        "link": f"https://palmeiras.com.br/noticias/{slug}/",
        "title": {"rendered": title},
        "content": {"rendered": html},
    }


class FakeSource:
    name = "fake"
    lookback_days = 7

    def __init__(self, posts: list[dict]) -> None:
        self.posts = posts

    def fetch_posts(self) -> list[dict]:
        return self.posts


class FakeNotifier:
    def __init__(self, fail_first: int = 0) -> None:
        self.messages: list[str] = []
        self.calls = 0
        self.fail_first = fail_first

    def send(self, text: str) -> str:
        self.calls += 1
        if self.calls <= self.fail_first:
            raise RuntimeError("telegram down")
        self.messages.append(text)
        return "1"


class CollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.tmp.name) / "test.db"))
        self.logger = logging.getLogger("test_collector")
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self) -> None:
        self.storage.close()
        self.tmp.cleanup()

    def collector(self, posts: list[dict], notifier: FakeNotifier) -> Collector:
        return Collector([FakeSource(posts)], self.storage, notifier, self.logger)

    def test_live_store_queue_alerts_once_and_retries_after_send_failure(self) -> None:
        class Store:
            name = "ticket_store"

            def check(self) -> StoreStatus:
                return StoreStatus(True, "202611061000", datetime(2026, 11, 6, 10), "https://ingressospalmeiras.com.br/jogo")

        notifier = FakeNotifier(fail_first=1)
        announcement = post("remo", "Ingressos para jogo contra Remo", UNPARSED_HTML)
        collector = Collector([FakeSource([announcement])], self.storage, notifier, self.logger, store_source=Store())
        collector.run_once(datetime(2026, 11, 6, 10))
        self.assertEqual(notifier.messages, [])
        collector.run_once(datetime(2026, 11, 6, 10, 5))
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("Vendas abertas", notifier.messages[0])
        self.assertIn("https://palmeiras.com.br/noticias/remo/", notifier.messages[0])
        collector.run_once(datetime(2026, 11, 6, 10, 10))
        self.assertEqual(len(notifier.messages), 1)

    def test_first_run_bootstraps_without_fallback(self) -> None:
        notifier = FakeNotifier()
        collector = self.collector([post("velho", "Ingressos para jogo", UNPARSED_HTML)], notifier)
        self.assertEqual(collector.run_once(datetime(2026, 10, 28)), [])
        self.assertEqual(notifier.messages, [])
        self.assertEqual(self.storage.count_posts(), 1)

    def test_new_unparsed_post_sends_fallback_once(self) -> None:
        old = post("velho", "Ingressos para jogo antigo", UNPARSED_HTML)
        new = post("novo", "Ingressos para jogo contra Fluminense", UNPARSED_HTML)
        notifier = FakeNotifier()
        collector = self.collector([old], notifier)
        collector.run_once(datetime(2026, 10, 28))

        collector = self.collector([old, new], notifier)
        collector.run_once(datetime(2026, 10, 28))
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("não identifiquei a janela Diamante", notifier.messages[0])
        self.assertIn("https://palmeiras.com.br/noticias/novo/", notifier.messages[0])

        collector.run_once(datetime(2026, 10, 28))
        self.assertEqual(len(notifier.messages), 1)

    def test_parsed_event_sent_once(self) -> None:
        notifier = FakeNotifier()
        parsed = post("remo", "Ingressos para jogo contra Remo", PARSED_HTML)
        collector = self.collector([parsed], notifier)
        sent = collector.run_once(datetime(2026, 10, 28))
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("Mandante", notifier.messages[0])

        collector.run_once(datetime(2026, 10, 28))
        self.assertEqual(len(notifier.messages), 1)

    def test_post_without_ingresso_is_silent(self) -> None:
        old = post("velho", "Ingressos para jogo antigo", UNPARSED_HTML)
        other = post("outro", "Notícia sobre o time", "<p>Treino aberto.</p>")
        notifier = FakeNotifier()
        collector = self.collector([old], notifier)
        collector.run_once(datetime(2026, 10, 28))
        collector = self.collector([old, other], notifier)
        collector.run_once(datetime(2026, 10, 28))
        self.assertEqual(notifier.messages, [])

    def test_fallback_retries_after_send_failure(self) -> None:
        old = post("velho", "Ingressos para jogo antigo", UNPARSED_HTML)
        new = post("novo", "Ingressos para jogo contra Fluminense", UNPARSED_HTML)
        notifier = FakeNotifier(fail_first=1)
        collector = self.collector([old], notifier)
        collector.run_once(datetime(2026, 10, 28))

        collector = self.collector([old, new], notifier)
        collector.run_once(datetime(2026, 10, 28))
        self.assertEqual(notifier.messages, [])

        collector.run_once(datetime(2026, 10, 28))
        self.assertEqual(len(notifier.messages), 1)

    def test_event_failure_does_not_block_next_event(self) -> None:
        remo = post("remo", "Ingressos para jogo contra Remo", PARSED_HTML)
        vasco = post(
            "vasco",
            "Ingressos para jogo contra Vasco",
            PARSED_HTML.replace("Remo", "Vasco"),
        )
        notifier = FakeNotifier(fail_first=1)
        collector = self.collector([remo, vasco], notifier)
        sent = collector.run_once(datetime(2026, 10, 28))
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(notifier.messages), 1)


class FailingSource:
    name = "quebrada"
    lookback_days = 7

    def fetch_posts(self) -> list[dict]:
        raise RuntimeError("api fora do ar")


class CollectorHealthAlertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.tmp.name) / "test.db"))
        self.logger = logging.getLogger("test_health")
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self) -> None:
        self.storage.close()
        self.tmp.cleanup()

    def test_source_failure_sends_alert_once_per_day(self) -> None:
        notifier = FakeNotifier()
        collector = Collector([FailingSource()], self.storage, notifier, self.logger)

        collector.run_once(datetime(2026, 10, 28, 9, 0))
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn('a fonte "quebrada" falhou', notifier.messages[0])
        self.assertIn("RuntimeError: api fora do ar", notifier.messages[0])

        collector.run_once(datetime(2026, 10, 28, 15, 0))
        self.assertEqual(len(notifier.messages), 1)

        collector.run_once(datetime(2026, 10, 29, 9, 0))
        self.assertEqual(len(notifier.messages), 2)

    def test_empty_feed_sends_alert_once_per_day(self) -> None:
        notifier = FakeNotifier()
        collector = self.collector_empty(notifier)

        collector.run_once(datetime(2026, 10, 28, 9, 0))
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("não retornou nenhum post", notifier.messages[0])

        collector.run_once(datetime(2026, 10, 28, 21, 0))
        self.assertEqual(len(notifier.messages), 1)

    def test_health_alert_retries_after_send_failure(self) -> None:
        notifier = FakeNotifier(fail_first=1)
        collector = Collector([FailingSource()], self.storage, notifier, self.logger)

        collector.run_once(datetime(2026, 10, 28, 9, 0))
        self.assertEqual(notifier.messages, [])

        collector.run_once(datetime(2026, 10, 28, 15, 0))
        self.assertEqual(len(notifier.messages), 1)

    def test_healthy_source_does_not_alert(self) -> None:
        notifier = FakeNotifier()
        collector = Collector(
            [FakeSource([post("ok", "Ingressos", PARSED_HTML)])],
            self.storage,
            notifier,
            self.logger,
        )
        collector.run_once(datetime(2026, 10, 28, 9, 0))
        self.assertFalse(any("Monitor:" in message for message in notifier.messages))

    def collector_empty(self, notifier: FakeNotifier) -> Collector:
        return Collector([FakeSource([])], self.storage, notifier, self.logger)


if __name__ == "__main__":
    unittest.main()
