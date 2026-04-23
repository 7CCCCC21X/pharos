# Pharos batch airdrop query

Batch query the Pharos airdrop endpoint for many addresses at once.

```
GET https://api.claim.pharos.xyz/airdrop/airdrop_info?address=<addr>
authorization: TOKEN <token>
```

The token is session-bound to one wallet, so for multi-wallet batches you
usually supply one token per address.

## Requirements

- Python 3.9+ (standard library only, no `pip install` needed)

## Input formats

**One address per line (use a single shared token):**

```
0x0EA2b31F35f96a12DA3EDd76154a81ACDA731197
0xabc...
```

**Per-address token** (separator can be space, tab, comma, or semicolon):

```
0x0EA2b31F35f96a12DA3EDd76154a81ACDA731197,mq0luhhd9a9l0268rzfcw1fubc6pj46i
0xabc...,<token-for-abc>
0xdef... <token-for-def>
```

Blank lines and `#` comment lines are ignored.

## Usage

```bash
# File with per-address tokens
python batch_airdrop_query.py -i wallets.txt -o result.csv

# File with just addresses, shared token via env var
PHAROS_TOKEN=mq0luhhd9a9l0268rzfcw1fubc6pj46i \
  python batch_airdrop_query.py -i addresses.txt -o result.csv

# Ad-hoc addresses on the command line
python batch_airdrop_query.py \
  --token mq0luhhd9a9l0268rzfcw1fubc6pj46i \
  -a 0x0EA2b31F35f96a12DA3EDd76154a81ACDA731197

# Through a local HTTP proxy (same as the browser trace)
python batch_airdrop_query.py -i wallets.txt --proxy http://127.0.0.1:7890

# JSON output, tuned concurrency / retries / timeout
python batch_airdrop_query.py -i wallets.txt -o result.json \
  -c 10 --retries 5 --timeout 20 --rate 0.1
```

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `-i, --input` | — | File with `<address>` or `<address><sep><token>` per line |
| `-a, --addresses` | — | Addresses on the command line (uses `--token`) |
| `-o, --output` | `airdrop_results.csv` | Output path. `.csv` or `.json` inferred from extension |
| `--token` | `$PHAROS_TOKEN` | Fallback token when the input file has no per-address token |
| `--proxy` | `$HTTPS_PROXY`/`$HTTP_PROXY` | HTTP(S) proxy URL, e.g. `http://127.0.0.1:7890` |
| `-c, --concurrency` | `5` | Parallel workers |
| `--timeout` | `15` | Per-request timeout (s) |
| `--retries` | `3` | Retries for network / 5xx / 429 failures |
| `--backoff` | `1.0` | Initial retry backoff (s), doubles each attempt |
| `--rate` | `0` | Optional submission delay between requests (s) |

## Output

### CSV

Columns: `address, ok, status, error, <top-level keys from airdrop_info>`.
Nested objects/arrays are JSON-encoded inside their cell.

### JSON

```json
[
  {
    "address": "0x...",
    "ok": true,
    "status": 200,
    "error": "",
    "data": { ... full response body ... }
  }
]
```

Exit code is `0` when every address succeeded, `1` if any failed, `2` for
argument / setup errors.
