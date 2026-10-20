"""Writes bundled-prices.json from AWS offer files already downloaded into a folder (named <offer>-<region>.json,
<offer>-global.json for CloudFront, AmazonEC2-<region>.csv for EC2) and the prices that only a page says (Cloudflare's,
Route 53's hosted zone). It does not fetch: the person who
refreshes the table downloads the files (aws_offers.OFFER_URL) and runs

    python -m jsonui_doc_cli.infra.cost.build_bundled <folder> <the day Cloudflare's pages were read> [<the day
        AWS's pages (Route 53's hosted zone) were read; the first day when not given>]

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
R53 = "https://aws.amazon.com/route53/pricing/"
#: The EC2 instance types bundled (the offer has hundreds; the rest come from the fetch's large "ec2"): the small and
#: the usual ones of a backend's first years. NAT gateway and gp3 rows come from the same file.
EC2_TYPES = ("t3.nano", "t3.micro", "t3.small", "t3.medium", "t3.large", "t4g.nano", "t4g.micro", "t4g.small",
             "t4g.medium", "t4g.large", "m7g.large", "m7i.large", "c7g.large", "r7g.large")


def aws_page_rows(checked: str) -> list[dict]:
    """AWS prices no offer file holds: Route 53's hosted zone (the page, read on ``checked``)."""
    return [{"provider": "aws", "service": "route53", "sku": "zone", "region": "global", "unit": "month",
             "tiers": [{"from": 0.0, "to": 25.0, "price_usd": 0.5}, {"from": 25.0, "price_usd": 0.1}],
             "effective": checked, "source": R53, "note": "hosted zone: the first 25, then each"}]


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
    for region in REGIONS:
        f = folder / f"AmazonEC2-{region}.csv"
        if not f.is_file():
            missing.append(f"{f.name}: not downloaded")
            continue
        with f.open(encoding="utf-8", newline="") as lines:
            got, miss = A.rows_from_ec2_csv(lines, region, A.EC2_CSV_URL.format(region=region))
        rows += [r for r in got if r["service"] != "ec2" or r["sku"] in EC2_TYPES or r["sku"] == "storage"]
        kept = {r["sku"] for r in got if r["service"] == "ec2"}
        missing += [f"{region}: {m}" for m in miss] + [f"{region}: ec2 {t}" for t in EC2_TYPES if t not in kept]
    f = folder / "AmazonCloudFront-global.json"
    if f.is_file():
        got, miss = A.rows_from_offer(json.loads(f.read_text()), A.cloudfront_spec(), "global",
                                      A.GLOBAL_OFFER_URL.format(offer="AmazonCloudFront"))
        rows += got
        missing += [f"global: {m}" for m in miss]
    else:
        missing.append(f"{f.name}: not downloaded")
    return rows, missing


def build(folder: Path, checked: str, aws_checked: str | None = None) -> tuple[dict, list[str]]:
    rows, missing = aws_rows(folder)
    doc = {"$schema": "https://jsonui.dev/schemas/infra-prices/v0.json", "version": 0, "id": "bundled",
           "label": "同梱の単価（AWS ap-northeast-1・us-east-1 と Cloudflare、オンデマンド）", "currency": "USD",
           "prices": rows + aws_page_rows(aws_checked or checked) + cloudflare_rows(checked)}
    return doc, missing


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):   # the days are the person's to say (the pages they read), never the machine's clock
        print("usage: build_bundled <folder of offer files> <YYYY-MM-DD Cloudflare's pages were read> "
              "[<YYYY-MM-DD AWS's pages were read>]", file=sys.stderr)
        return 2
    folder, checked = Path(argv[0]), argv[1]
    doc, missing = build(folder, checked, argv[2] if len(argv) == 3 else None)
    out = Path(__file__).with_name("bundled-prices.json")
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(doc['prices'])} prices)")
    for m in missing:
        print(f"missing: {m}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
