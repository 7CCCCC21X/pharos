#!/usr/bin/env python3
"""Batch query Pharos airdrop_info for a list of EVM addresses.

Endpoint:
    GET https://api.claim.pharos.xyz/airdrop/airdrop_info?address=<addr>

Auth:
    Header "authorization: TOKEN <token>"

The authorization token from claim.pharos.xyz is session-bound to a single
wallet, so you usually need one token per address. This tool supports either:

  - a single shared token via --token / $PHAROS_TOKEN, or
  - per-address tokens in the input file:
        0xabc...<tab or comma or space>TOKEN_VALUE
    Blank lines and lines starting with '#' are ignored.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import urllib.error
import urllib.request


API_URL = "https://api.claim.pharos.xyz/airdrop/airdrop_info"
DEFAULT_ORIGIN = "https://claim.pharos.xyz"
DEFAULT_REFERER = "https://claim.pharos.xyz/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)

ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")


@dataclass
class QueryResult:
    address: str
    ok: bool
    status: int = 0
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def load_entries(path: str) -> list[tuple[str, str | None]]:
    """Return (address, token-or-None) pairs from the input file.

    Accepts lines like:
        0xabc...
        0xabc...,TOKEN
        0xabc... TOKEN
        0xabc...\tTOKEN
    """
    entries: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = ADDRESS_RE.search(line)
            if not match:
                continue
            addr = match.group(0)
            key = addr.lower()
            if key in seen:
                continue
            seen.add(key)
            # Everything after the address (skipping separators) is the token.
            remainder = line[match.end():].lstrip(" \t,;").strip()
            token = remainder or None
            entries.append((addr, token))
    return entries


def build_opener(proxy: str | None) -> urllib.request.OpenerDirector:
    handlers: list[urllib.request.BaseHandler] = []
    if proxy:
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    else:
        # Explicitly disable proxies unless one was requested, so we don't
        # silently inherit a broken HTTP_PROXY from the environment.
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def build_request(address: str, token: str) -> urllib.request.Request:
    url = f"{API_URL}?{urlencode({'address': address})}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "authorization": f"TOKEN {token}",
        "origin": DEFAULT_ORIGIN,
        "referer": DEFAULT_REFERER,
        "user-agent": DEFAULT_USER_AGENT,
    }
    return urllib.request.Request(url, headers=headers, method="GET")


def query_one(
    address: str,
    token: str,
    opener: urllib.request.OpenerDirector,
    *,
    timeout: float,
    retries: int,
    backoff: float,
) -> QueryResult:
    attempt = 0
    last_err = ""
    last_status = 0
    while attempt <= retries:
        try:
            req = build_request(address, token)
            with opener.open(req, timeout=timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    parsed = {"_raw": body}
                return QueryResult(
                    address=address, ok=True, status=status, data=parsed
                )
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            try:
                last_err = exc.read().decode("utf-8", errors="replace")
            except Exception:
                last_err = str(exc)
            # 4xx (except 429) are not retried — the result is stable.
            if exc.code != 429 and 400 <= exc.code < 500:
                return QueryResult(
                    address=address,
                    ok=False,
                    status=exc.code,
                    error=last_err,
                )
        except urllib.error.URLError as exc:
            last_err = f"URLError: {exc.reason}"
        except Exception as exc:  # pragma: no cover - defensive
            last_err = f"{type(exc).__name__}: {exc}"

        attempt += 1
        if attempt > retries:
            break
        sleep_for = backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
        time.sleep(sleep_for)

    return QueryResult(
        address=address, ok=False, status=last_status, error=last_err
    )


def flatten_for_csv(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten the top-level dict to primitive columns for CSV output."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[key] = value
    return flat


def write_csv(results: list[QueryResult], path: str) -> None:
    rows = [
        {
            "address": r.address,
            "ok": r.ok,
            "status": r.status,
            "error": r.error,
            **flatten_for_csv(r.data),
        }
        for r in results
    ]
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(results: list[QueryResult], path: str) -> None:
    payload = [
        {
            "address": r.address,
            "ok": r.ok,
            "status": r.status,
            "error": r.error,
            "data": r.data,
        }
        for r in results
    ]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch query Pharos airdrop_info for a list of addresses.",
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "-i",
        "--input",
        help="Path to a file. Each line: '<address>' or '<address><sep><token>'.",
    )
    src.add_argument(
        "-a",
        "--addresses",
        nargs="+",
        help="Addresses to query (space separated). Uses --token for all.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="airdrop_results.csv",
        help="Output file path. Format inferred from extension (.csv or .json). Default: airdrop_results.csv",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("PHAROS_TOKEN", ""),
        help="Fallback TOKEN value when the input file has no per-address token. Defaults to $PHAROS_TOKEN.",
    )
    parser.add_argument(
        "--proxy",
        default=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "",
        help="HTTP(S) proxy URL, e.g. http://127.0.0.1:7890. Defaults to $HTTPS_PROXY/$HTTP_PROXY.",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent requests (default: 5).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Per-request timeout in seconds (default: 15).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retry count for transient failures (default: 3).",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=1.0,
        help="Initial retry backoff in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=0.0,
        help="Optional delay in seconds between submissions (default: 0).",
    )
    return parser.parse_args(argv)


def resolve_entries(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Produce (address, token) pairs for every address to be queried."""
    raw: list[tuple[str, str | None]]
    if args.input:
        raw = load_entries(args.input)
    else:
        raw = []
        seen: set[str] = set()
        for item in args.addresses:
            for addr in ADDRESS_RE.findall(item):
                key = addr.lower()
                if key not in seen:
                    seen.add(key)
                    raw.append((addr, None))

    resolved: list[tuple[str, str]] = []
    missing: list[str] = []
    for addr, tok in raw:
        final = tok or args.token
        if not final:
            missing.append(addr)
            continue
        resolved.append((addr, final))

    if missing:
        preview = ", ".join(missing[:3]) + (" ..." if len(missing) > 3 else "")
        print(
            f"error: no token for {len(missing)} address(es) ({preview}). "
            "Add tokens in the input file or pass --token / $PHAROS_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(2)

    return resolved


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    entries = resolve_entries(args)
    if not entries:
        print("error: no valid addresses found.", file=sys.stderr)
        return 2

    opener = build_opener(args.proxy or None)

    via = f" via {args.proxy}" if args.proxy else ""
    print(
        f"Querying {len(entries)} address(es) with concurrency={args.concurrency}{via}...",
        file=sys.stderr,
    )

    results: list[QueryResult] = []
    ok_count = 0
    fail_count = 0
    t0 = time.time()

    with cf.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        future_to_addr = {}
        for addr, token in entries:
            future = pool.submit(
                query_one,
                addr,
                token,
                opener,
                timeout=args.timeout,
                retries=args.retries,
                backoff=args.backoff,
            )
            future_to_addr[future] = addr
            if args.rate > 0:
                time.sleep(args.rate)

        for future in cf.as_completed(future_to_addr):
            result = future.result()
            results.append(result)
            if result.ok:
                ok_count += 1
                status_label = "OK"
            else:
                fail_count += 1
                status_label = f"FAIL({result.status or 'ERR'})"
            print(
                f"[{ok_count + fail_count}/{len(entries)}] {result.address} {status_label}",
                file=sys.stderr,
            )

    # Keep output order aligned with input order.
    order = {addr: i for i, (addr, _) in enumerate(entries)}
    results.sort(key=lambda r: order.get(r.address, 1 << 30))

    ext = os.path.splitext(args.output)[1].lower()
    if ext == ".json":
        write_json(results, args.output)
    else:
        write_csv(results, args.output)

    elapsed = time.time() - t0
    print(
        f"Done. ok={ok_count} fail={fail_count} elapsed={elapsed:.1f}s output={args.output}",
        file=sys.stderr,
    )
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
