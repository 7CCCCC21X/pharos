"""Tests for batch_airdrop_query.

Run with:
    python -m unittest test_batch_airdrop_query -v
"""

from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest

import batch_airdrop_query as m


class LoadEntriesTests(unittest.TestCase):
    def _write(self, text: str) -> str:
        fh = tempfile.NamedTemporaryFile(
            "w", delete=False, suffix=".txt", encoding="utf-8"
        )
        fh.write(text)
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_address_only_lines(self) -> None:
        path = self._write(
            "0x0EA2b31F35f96a12DA3EDd76154a81ACDA731197\n"
            "0x1111111111111111111111111111111111111111\n"
        )
        entries = m.load_entries(path)
        self.assertEqual(
            entries,
            [
                ("0x0EA2b31F35f96a12DA3EDd76154a81ACDA731197", None),
                ("0x1111111111111111111111111111111111111111", None),
            ],
        )

    def test_various_separators(self) -> None:
        path = self._write(
            "0x0000000000000000000000000000000000000001,tokenA\n"
            "0x0000000000000000000000000000000000000002\ttokenB\n"
            "0x0000000000000000000000000000000000000003 tokenC\n"
            "0x0000000000000000000000000000000000000004;tokenD\n"
        )
        entries = m.load_entries(path)
        self.assertEqual(
            entries,
            [
                ("0x0000000000000000000000000000000000000001", "tokenA"),
                ("0x0000000000000000000000000000000000000002", "tokenB"),
                ("0x0000000000000000000000000000000000000003", "tokenC"),
                ("0x0000000000000000000000000000000000000004", "tokenD"),
            ],
        )

    def test_ignores_comments_blanks_and_dedupes(self) -> None:
        addr = "0x0EA2b31F35f96a12DA3EDd76154a81ACDA731197"
        path = self._write(
            "# header comment\n"
            "\n"
            f"{addr},tokenA\n"
            f"{addr.lower()},tokenB\n"  # duplicate (case-insensitive) — dropped
            "   # indented comment is treated as content only if it has an addr\n"
        )
        entries = m.load_entries(path)
        self.assertEqual(entries, [(addr, "tokenA")])


class ResolveEntriesTests(unittest.TestCase):
    def test_cli_addresses_use_fallback_token(self) -> None:
        ns = argparse.Namespace(
            input=None,
            addresses=[
                "0x1111111111111111111111111111111111111111",
                "0x2222222222222222222222222222222222222222",
            ],
            token="SHARED",
        )
        self.assertEqual(
            m.resolve_entries(ns),
            [
                ("0x1111111111111111111111111111111111111111", "SHARED"),
                ("0x2222222222222222222222222222222222222222", "SHARED"),
            ],
        )

    def test_missing_token_exits(self) -> None:
        ns = argparse.Namespace(
            input=None,
            addresses=["0x1111111111111111111111111111111111111111"],
            token="",
        )
        with self.assertRaises(SystemExit) as ctx:
            m.resolve_entries(ns)
        self.assertEqual(ctx.exception.code, 2)


class BuildRequestTests(unittest.TestCase):
    def test_url_and_headers(self) -> None:
        addr = "0x0EA2b31F35f96a12DA3EDd76154a81ACDA731197"
        req = m.build_request(addr, "abc123")
        self.assertEqual(
            req.full_url,
            "https://api.claim.pharos.xyz/airdrop/airdrop_info"
            f"?address={addr}",
        )
        self.assertEqual(req.get_method(), "GET")
        headers_lower = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(headers_lower["authorization"], "TOKEN abc123")
        self.assertEqual(headers_lower["origin"], "https://claim.pharos.xyz")
        self.assertEqual(headers_lower["referer"], "https://claim.pharos.xyz/")


class CheckpointTests(unittest.TestCase):
    def test_round_trip_and_resume_semantics(self) -> None:
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(lambda: _rmtree(tmpdir))
        path = os.path.join(tmpdir, "ckpt.jsonl")

        writer = m.CheckpointWriter(path)
        writer.append(
            m.QueryResult(
                address="0xAAAAaaaaAAAAaaaaAAAAaaaaAAAAaaaaAAAAaaaa",
                ok=True,
                status=200,
                data={"eligible": True, "amount": "100"},
            )
        )
        writer.append(
            m.QueryResult(
                address="0xBBBBbbbbBBBBbbbbBBBBbbbbBBBBbbbbBBBBbbbb",
                ok=False,
                status=500,
                error="boom",
            )
        )
        # A later entry for the same address should overwrite the earlier one.
        writer.append(
            m.QueryResult(
                address="0xAAAAaaaaAAAAaaaaAAAAaaaaAAAAaaaaAAAAaaaa",
                ok=True,
                status=200,
                data={"eligible": True, "amount": "200"},
            )
        )
        writer.close()

        loaded = m.load_checkpoint(path)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(
            loaded["0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"].data["amount"],
            "200",
        )
        self.assertFalse(loaded["0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"].ok)

    def test_missing_checkpoint_is_empty(self) -> None:
        self.assertEqual(m.load_checkpoint("/no/such/file.jsonl"), {})


class FlattenForCsvTests(unittest.TestCase):
    def test_nested_values_are_json_encoded(self) -> None:
        flat = m.flatten_for_csv(
            {"eligible": True, "amount": "42", "meta": {"nested": [1, 2]}}
        )
        self.assertEqual(flat["eligible"], True)
        self.assertEqual(flat["amount"], "42")
        self.assertEqual(json.loads(flat["meta"]), {"nested": [1, 2]})


def _rmtree(path: str) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
