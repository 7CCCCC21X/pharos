# Pharos batch airdrop query

Batch query the Pharos airdrop endpoint for many addresses at once.

```
GET https://api.claim.pharos.xyz/airdrop/airdrop_info?address=<addr>
authorization: TOKEN <token>
```

## Requirements

- Python 3.9+ (uses standard library only — no pip install required)

## Usage

```bash
# From a file of addresses (one per line)
PHAROS_TOKEN=mq0luhhd9a9l0268rzfcw1fubc6pj46i \
  python batch_airdrop_query.py -i addresses.txt -o result.csv

# Addresses on the command line
python batch_airdrop_query.py \
  --token mq0luhhd9a9l0268rzfcw1fubc6pj46i \
  -a 0x0EA2b31F35f96a12DA3EDd76154a81ACDA731197 0xabc...

# JSON output
python batch_airdrop_query.py -i addresses.txt -o result.json

# Tune concurrency / retries / timeout
python batch_airdrop_query.py -i addresses.txt -c 10 --retries 5 --timeout 20
```

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `-i, --input` | — | File with one address per line (blank/`#` lines ignored) |
| `-a, --addresses` | — | Addresses passed on the command line |
| `-o, --output` | `airdrop_results.csv` | Output path. `.csv` or `.json` inferred from extension |
| `--token` | `$PHAROS_TOKEN` | `authorization: TOKEN <value>` header |
| `-c, --concurrency` | `5` | Parallel workers |
| `--timeout` | `15` | Per-request timeout (s) |
| `--retries` | `3` | Retries for network / 5xx / 429 failures |
| `--backoff` | `1.0` | Initial retry backoff (s), doubles each attempt |
| `--rate` | `0` | Optional submission delay per worker (s) |

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
argument/setup errors.
