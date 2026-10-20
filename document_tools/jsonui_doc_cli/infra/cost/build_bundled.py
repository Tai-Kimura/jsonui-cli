"""Writes bundled-prices.json from AWS offer files already downloaded into a folder (named <offer>-<region>.json,
<offer>-global.json for CloudFront) and Cloudflare's prices as its pages say them. It does not fetch: the person who
refreshes the table downloads the files (aws_offers.OFFER_URL) and runs

    python -m jsonui_doc_cli.infra.cost.build_bundled <folder> <the day the pages were read, YYYY-MM-DD>

Every row keeps its source (the offer file's URL, or the page) and its effective date (the offer's publication date,
or the day the page was read).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import aws_offers as A

REGIONS = ("ap-northeast-1", "us-east-1")
CF_WORKERS = "https://developers.cloudflare.com/workers/platform/pricing/"
CF_R2 = "https://developers.cloudflare.com/r2/pricing/"
CF_D1 = "https://developers.cloudflare.com/d1/platform/pricing/"
CF_QUEUES = "https://developers.cloudflare.com/queues/platform/pricing/"


def cloudflare_rows(checked: str) -> list[dict]:
    """Workers Paid (Standard), R2 Standard, D1 and Queues on Workers Paid, as the pages said them on ``checked``."""
    def row(service, sku, unit, price, source, per_units=None, free=None, note=None):
        r = {"provider": "cloudflare", "service": service, "sku": sku, "region": "global", "unit": unit,
             "price_usd": price, "effective": checked, "source": source}
        if per_units:
            r["per_units"] = per_units
        if free:
            r["free"] = {"amount": free, "period": "month"}
        if note:
            r["note"] = note
        return r
    return [
        row("workers", "plan", "month", 5.0, CF_WORKERS, note="Workers Paid: the monthly minimum"),
        row("workers", "requests", "request", 0.30, CF_WORKERS, 1_000_000, 10_000_000, "10 million included"),
        row("workers", "cpu", "ms", 0.02, CF_WORKERS, 1_000_000, 30_000_000, "30 million CPU ms included"),
        row("r2", "storage", "GB-month", 0.015, CF_R2, free=10, note="Standard storage"),
        row("r2", "put", "request", 4.50, CF_R2, 1_000_000, 1_000_000, "Class A operations"),
        row("r2", "get", "request", 0.36, CF_R2, 1_000_000, 10_000_000, "Class B operations"),
        row("d1", "rows-read", "row", 0.001, CF_D1, 1_000_000, 25_000_000_000, "25 billion included"),
        row("d1", "rows-written", "row", 1.00, CF_D1, 1_000_000, 50_000_000, "50 million included"),
        row("d1", "storage", "GB-month", 0.75, CF_D1, free=5, note="5 GB included"),
        row("queues", "requests", "request", 0.40, CF_QUEUES, 1_000_000, 1_000_000,
            "operations (64 KB each); 1 million included"),
    ]


def aws_rows(folder: Path) -> tuple[list[dict], list[str]]:
    rows, missing = [], []
    spec = A.regional_spec()
    for region in REGIONS:
        for offer in sorted({s["offer"] for s in spec}):
            f = folder / f"{offer}-{region}.json"
            if not f.is_file():
                missing.append(f"{f.name}: not downloaded")
                continue
            got, miss = A.rows_from_offer(json.loads(f.read_text()), [s for s in spec if s["offer"] == offer], region,
                                          A.OFFER_URL.format(offer=offer, region=region))
            rows += got
            missing += [f"{region}: {m}" for m in miss]
    f = folder / "AmazonCloudFront-global.json"
    if f.is_file():
        got, miss = A.rows_from_offer(json.loads(f.read_text()), A.cloudfront_spec(), "global",
                                      A.GLOBAL_OFFER_URL.format(offer="AmazonCloudFront"))
        rows += got
        missing += [f"global: {m}" for m in miss]
    else:
        missing.append(f"{f.name}: not downloaded")
    return rows, missing


def build(folder: Path, checked: str) -> tuple[dict, list[str]]:
    rows, missing = aws_rows(folder)
    doc = {"$schema": "https://jsonui.dev/schemas/infra-prices/v0.json", "version": 0, "id": "bundled",
           "label": "同梱の単価（AWS ap-northeast-1・us-east-1 と Cloudflare、オンデマンド）", "currency": "USD",
           "prices": rows + cloudflare_rows(checked)}
    return doc, missing


def main(argv: list[str]) -> int:
    if len(argv) != 2:          # the day is the person's to say (the pages they read), never the machine's clock
        print("usage: build_bundled <folder of offer files> <YYYY-MM-DD the Cloudflare pages were read>", file=sys.stderr)
        return 2
    folder, checked = Path(argv[0]), argv[1]
    doc, missing = build(folder, checked)
    out = Path(__file__).with_name("bundled-prices.json")
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(doc['prices'])} prices)")
    for m in missing:
        print(f"missing: {m}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
