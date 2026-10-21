"""The prices fetched (plan docs/plans/2026-10-20-jui-viz-backend-load-and-cost-simulator.md, L-B2): Azure Retail
Prices and AWS's offer files into infra-prices.v0 files in the cache the price book reads. Nothing here goes outside:
the answers are real extracts kept in fixtures/infra/price-fetch (fetched 2026-10-20 from the public URLs), served by
a fake get."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import prices as P
from jsonui_doc_cli.infra.cost import aws_offers as AWS
from jsonui_doc_cli.infra.cost import azure_prices as AZ
from jsonui_doc_cli.infra.cost import fetch as F
from jsonui_doc_cli.infra.cost import pricebook

FX = Path(__file__).parent / "fixtures" / "infra" / "price-fetch"


def azure_items(name: str) -> list[dict]:
    return json.loads((FX / f"azure-{name}-japaneast.json").read_text())["Items"]


# ---------------------------------------------------------------- Azure: units, free steps, the spec

@pytest.mark.parametrize("uom, want", [("10", 10), ("10K", 10_000), ("1M", 1_000_000), ("1 GB/Month", 1),
                                       ("1 Hour", 1), ("1 GB Second", 1), ("1/Hour", 1), ("100", 100), ("GB", None), ("", None)])
def test_a_unit_of_measure_is_a_block_of_plain_units(uom, want):
    assert AZ.block(uom) == want


def test_functions_free_million_executions_is_a_zero_step_in_plain_units():
    rows, missing = AZ.rows_from_items(azure_items("functions"), "Functions", "japaneast", "U")
    assert missing == []
    req = next(r for r in rows if r["sku"] == "requests")
    # "Standard Total Executions": 0 USD for 100000 blocks of 10, then 2e-06 per 10 -> 0.20 per million
    assert req["unit"] == "request" and req["per_units"] == 1_000_000
    assert req["tiers"] == [{"from": 0.0, "price_usd": 0.0, "to": 1_000_000.0}, {"from": 1_000_000.0, "price_usd": 0.2}]
    gbs = next(r for r in rows if r["sku"] == "compute")
    assert gbs["tiers"] == [{"from": 0.0, "price_usd": 0.0, "to": 400_000.0}, {"from": 400_000.0, "price_usd": 1.6e-05}]
    assert gbs["effective"] == "2017-01-01" and gbs["provider"] == "azure" and gbs["service"] == "functions"


def test_every_spec_line_is_found_in_the_real_answers():
    names = {"Functions": "functions", "Storage": "storage", "Service Bus": "service-bus", "Key Vault": "key-vault",
             "Azure Cosmos DB": "azure-cosmos-db", "Bandwidth": "bandwidth"}
    assert set(names) == set(AZ.SERVICES)
    all_rows = []
    for svc, name in names.items():
        rows, missing = AZ.rows_from_items(azure_items(name), svc, "japaneast", AZ.query_url(svc, "japaneast"))
        assert missing == [], (svc, missing)
        all_rows += rows
    assert len(all_rows) == len(AZ.SPEC)
    doc, problems = P.read_file("x.json", json.dumps({"version": 0, "prices": all_rows}).encode())
    assert doc is not None, problems
    egress = next(r for r in all_rows if r["sku"] == "egress")
    assert egress["service"] == "data-transfer" and egress["tiers"][0] == {"from": 0.0, "price_usd": 0.0, "to": 100.0}
    assert [t["from"] for t in egress["tiers"]] == sorted(t["from"] for t in egress["tiers"])


def test_only_pay_as_you_go_in_the_asked_region_and_the_spec_unit():
    items = azure_items("key-vault")
    other = [dict(i, armRegionName="eastus") for i in items] + [dict(i, type="Reservation") for i in items]
    assert AZ.rows_from_items(other, "Key Vault", "japaneast", "U")[0] == []
    wrong_unit = [dict(i, unitOfMeasure="1") if i["meterName"] == "Operations" else i for i in items]
    rows, missing = AZ.rows_from_items(wrong_unit, "Key Vault", "japaneast", "U")
    assert rows == [] and "unit" in missing[0]   # another unit is not guessed


def test_the_query_names_one_service_one_region_and_narrows_storage():
    url = AZ.query_url("Storage", "japaneast")
    assert url.startswith("https://prices.azure.com/api/retail/prices?%24filter=")
    assert "Blob+Storage" in url and "japaneast" in url and "Consumption" in url


# ---------------------------------------------------------------- AWS: EC2's CSV, the offers

def test_ec2_keeps_linux_shared_on_demand_one_row_per_type():
    with (FX / "aws-ec2-ap-northeast-1-extract.csv").open(newline="") as fh:
        rows, why = AWS.rows_from_ec2_csv(fh, "ap-northeast-1", "U")
    other = [r for r in rows if r["service"] != "ec2" or r["sku"] == "storage"]
    rows = [r for r in rows if r not in other]
    by = {r["sku"]: r for r in rows}
    assert why == [] and by["t3.micro"]["price_usd"] == 0.0136 and by["m5.large"]["price_usd"] == 0.124
    assert all(r["unit"] == "instance-hour" and r["service"] == "ec2" and r["effective"] == "2026-10-15" for r in rows)
    # the NAT gateway's and gp3's rows, from the offer's own lines (10-21): $0.062 an hour and a GB, gp3 $0.096 a GB-month
    assert {(r["service"], r["sku"], r["unit"], r["price_usd"]) for r in other} == {
        ("vpc.nat", "hour", "instance-hour", 0.062), ("vpc.nat", "processed", "GB", 0.062),
        ("ebs", "storage", "GB-month", 0.096), ("ec2", "storage", "GB-month", 0.096)}
    text = (FX / "aws-ec2-ap-northeast-1-extract.csv").read_text()
    assert '"Windows"' in text and '"Reserved"' in text and "DedicatedUsage:i8g.48xlarge" in text   # rows not to keep
    assert set(by) == {"c6g.large", "i7i.48xlarge", "m5.large", "r5a.xlarge", "t3.micro"}   # no dedicated i8g.48xlarge
    assert len(rows) == len(by)


def test_ec2_with_another_header_is_said_not_guessed():
    rows, why = AWS.rows_from_ec2_csv(['"SKU","Price"', '"x","1"'], "ap-northeast-1", "U")
    assert rows == [] and "header" in why[0]


def test_the_lambda_offer_extract():
    data = json.loads((FX / "aws-lambda-ap-northeast-1.json").read_text())
    spec = [s for s in AWS.regional_spec() if s["offer"] == "AWSLambda"]
    rows, missing = AWS.rows_from_offer(data, spec, "ap-northeast-1", "U")
    assert missing == [] and {r["sku"] for r in rows} == {"requests", "compute", "compute:arm64"}
    arm = next(r for r in rows if r["sku"] == "compute:arm64")
    assert arm["tiers"][0]["price_usd"] == 0.0000133334 and arm["free"] == {"amount": 400_000, "period": "month"}


# ---------------------------------------------------------------- what is fetched

def test_the_default_setting_is_on_and_leaves_the_large_offers_out():
    s = F.setting_of(None)
    assert s == {"on": True, "regions": {"aws": ["ap-northeast-1", "us-east-1"], "azure": ["japaneast", "eastus"]},
                 "large": []}
    urls = [t["url"] for t in F.targets(s)]
    assert not any("AmazonRDS" in u or "AmazonEC2" in u for u in urls)
    assert sum("AmazonCloudFront" in u for u in urls) == 1
    assert F.setting_of({"on": False})["on"] is False
    chosen = F.setting_of({"large": ["ec2", "rds", "s3"], "regions": {"aws": ["eu-west-1", "../x"], "azure": []}})
    assert chosen["large"] == ["ec2", "rds"] and chosen["regions"] == {"aws": ["eu-west-1"], "azure": []}
    urls = [t["url"] for t in F.targets(chosen)]
    assert any("AmazonEC2/current/eu-west-1/index.csv" in u for u in urls) and any("AmazonRDS" in u for u in urls)
    assert not any("prices.azure.com" in u for u in urls)


def test_only_one_provider_or_region_when_asked():
    s = F.setting_of(None)
    assert {t["provider"] for t in F.targets(s, provider="azure")} == {"azure"}
    assert {t["region"] for t in F.targets(s, region="japaneast")} == {"japaneast"}


# ---------------------------------------------------------------- going outside

@pytest.mark.parametrize("url", ["http://prices.azure.com/api/retail/prices", "https://evil.example/api",
                                 "https://prices.azure.com.evil.example/x", "https://user:pw@prices.azure.com/x",
                                 "https://prices.azure.com:8443/x", "file:///etc/passwd"])
def test_only_https_to_the_two_price_hosts(url):
    with pytest.raises(F.Refused):
        F.check_url(url)


def test_the_two_hosts_pass():
    assert F.check_url(AZ.query_url("Functions", "japaneast"))
    assert F.check_url(AWS.OFFER_URL.format(offer="AWSLambda", region="ap-northeast-1"))


# ---------------------------------------------------------------- a run, with a fake get

def fake_get(answers: dict[str, bytes], seen: list | None = None):
    def get(url, limit):
        if seen is not None:
            seen.append(url)
        if url not in answers:
            raise OSError(f"no answer for {url}")
        body = answers[url]
        if len(body) > limit:
            raise F.Refused("over the cap")
        return body
    return get


def azure_answers() -> dict[str, bytes]:
    names = {"Functions": "functions", "Storage": "storage", "Service Bus": "service-bus", "Key Vault": "key-vault",
             "Azure Cosmos DB": "azure-cosmos-db", "Bandwidth": "bandwidth"}
    return {AZ.query_url(svc, "japaneast"): (FX / f"azure-{n}-japaneast.json").read_bytes() for svc, n in names.items()}


def azure_only():
    return F.setting_of({"regions": {"aws": [], "azure": ["japaneast"]}})


def test_a_run_writes_price_files_the_price_book_reads(tmp_path):
    answers = azure_answers()
    answers[F.AWS.GLOBAL_OFFER_URL.format(offer="AmazonCloudFront")] = b'{"products": {}, "terms": {}}'
    index = F.run(azure_only(), tmp_path, at_ms=1_792_500_000_000, get=fake_get(answers))
    assert index["files"]["azure/functions/japaneast.json"]["rows"] == 2
    assert index["files"]["azure/functions/japaneast.json"]["lastError"] is None
    assert index["files"]["aws/amazoncloudfront/global.json"]["lastError"] == "no price row in the answer"
    rows, why = pricebook.cache_rows(tmp_path)
    assert why == [] and len(rows) == len(AZ.SPEC)   # index.json is not read as a price file
    book = pricebook.Book(cache=rows)
    got = book.find("azure", "functions", "requests", "request", "japaneast", "2026-10-01")
    assert got["layer"] == "cache" and got["row"]["source"].startswith("https://prices.azure.com/")
    assert F.summary(index)["lastOkAt"] == 1_792_500_000_000 and F.summary(index)["failing"] == 1


def test_a_failure_keeps_the_last_file_and_says_why(tmp_path):
    answers = azure_answers()
    F.run(azure_only(), tmp_path, at_ms=1000, get=fake_get(answers))
    before = (tmp_path / "azure/functions/japaneast.json").read_bytes()
    answers.pop(AZ.query_url("Functions", "japaneast"))
    index = F.run(azure_only(), tmp_path, at_ms=2000, get=fake_get(answers))
    e = index["files"]["azure/functions/japaneast.json"]
    assert (tmp_path / "azure/functions/japaneast.json").read_bytes() == before
    assert e["fetchedAt"] == 1000 and e["lastTryAt"] == 2000 and e["rows"] == 2 and "OSError" in e["lastError"]
    assert index["files"]["azure/key-vault/japaneast.json"]["fetchedAt"] == 2000   # one failure stops nothing else


def test_a_secret_shaped_value_is_not_written(tmp_path):
    answers = azure_answers()
    page = json.loads(answers[AZ.query_url("Key Vault", "japaneast")])
    for i in page["Items"]:
        i["effectiveStartDate"] = "2020-01-01"
    url = AZ.query_url("Key Vault", "japaneast")
    answers[url] = json.dumps(page).encode()
    original = AZ.rows_from_items
    def leaky(items, svc, region, source):   # a row that would carry a secret's shape into the cache
        rows, missing = original(items, svc, region, source)
        return [dict(r, note="AKIA" "ABCDEFGHIJKLMNOP") for r in rows], missing
    AZ.rows_from_items = leaky
    try:
        index = F.run(azure_only(), tmp_path, at_ms=1000, get=fake_get(answers), provider="azure")
    finally:
        AZ.rows_from_items = original
    e = index["files"]["azure/key-vault/japaneast.json"]
    assert "secret" in e["lastError"] and not (tmp_path / "azure/key-vault/japaneast.json").exists()


def test_paging_follows_only_the_price_host_and_stops_at_the_cap(tmp_path):
    url = AZ.query_url("Key Vault", "japaneast")
    items = json.loads((FX / "azure-key-vault-japaneast.json").read_text())["Items"]
    pages = {url: json.dumps({"Items": items[:5], "NextPageLink": url + "&$skip=5"}).encode(),
             url + "&$skip=5": json.dumps({"Items": items[5:], "NextPageLink": None}).encode()}
    t = next(t for t in F.targets(azure_only()) if t["url"] == url)
    rows, missing = F.rows_of(t, fake_get(pages), None)
    assert len(rows) == 1 and missing == []
    away = {url: json.dumps({"Items": items, "NextPageLink": "https://evil.example/next"}).encode()}
    with pytest.raises(F.Refused):
        F.rows_of(t, fake_get(away), None)
    loop = {url: json.dumps({"Items": [], "NextPageLink": url}).encode()}
    calls: list = []
    def looping(u, limit):   # without the cap this would go on for ever: give up loudly instead of hanging the suite
        assert len(calls) < 50, "the page cap did not stop the pages"
        return fake_get(loop, calls)(u, limit)
    with pytest.raises(F.Refused, match="pages"):
        F.rows_of(t, looping, None)
    assert len(calls) == F.AZURE_PAGES


def test_an_answer_over_its_cap_is_refused(tmp_path):
    answers = azure_answers()
    t = next(t for t in F.targets(azure_only()) if t.get("service") == "Functions")
    with pytest.raises(F.Refused):
        F.rows_of(dict(t, limit=100), fake_get(answers), None)


def test_ec2_is_read_from_lines(tmp_path):
    s = F.setting_of({"regions": {"aws": ["ap-northeast-1"], "azure": []}, "large": ["ec2"]})
    t = next(t for t in F.targets(s) if t["kind"] == "ec2_csv")
    text = (FX / "aws-ec2-ap-northeast-1-extract.csv").read_text()
    got = F.fetch_one(t, tmp_path, 1000, get=fake_get({}), lines=lambda url, limit: iter(text.splitlines(True)))
    assert got["ok"] and got["rows"] >= 3 and (tmp_path / "aws/amazonec2/ap-northeast-1.json").exists()


def test_once_a_day():
    assert F.due({"files": {}}, 10)
    assert not F.due({"files": {}, "lastRunAt": 0, "lastRunWriter": F.WRITER}, F.EVERY_MS - 1)
    assert F.due({"files": {}, "lastRunAt": 0, "lastRunWriter": F.WRITER}, F.EVERY_MS)


# ---------------------------------------------------------------- the version that wrote the cache (ticket
# 2026-10-22-cloud-prices-cache-outlives-the-fetcher-that-wrote-it: 2.3.13 wrote the egress rows without the account's
# free amount, and an upgraded viz read them for up to a day)

def test_an_upgrade_makes_a_run_due_at_once_and_a_failed_run_waits_its_day():
    old = {"files": {}, "lastRunAt": 0, "lastRunWriter": "2.3.13"}
    assert F.due(old, 1) and F.due({"files": {}, "lastRunAt": 0}, 1)   # another version's run, or one before the mark
    failed = {"files": {"aws/x.json": {"writer": "2.3.13", "lastError": "URLError"}}, "lastRunAt": 0, "lastRunWriter": F.WRITER}
    assert not F.due(failed, 1)                                          # no fetch a minute: the bundled prices stand in


def test_a_run_marks_each_file_and_the_run_with_this_version(tmp_path):
    """Each file fetched names this version, and so does the run; a later failure keeps the last success's writer (its
    file is still another version's until fetched again)."""
    answers = azure_answers()
    index = F.run(azure_only(), tmp_path, at_ms=1000, get=fake_get(answers), provider="azure")
    e = index["files"]["azure/functions/japaneast.json"]
    assert e["writer"] == F.WRITER and index["lastRunWriter"] == F.WRITER and not F.due(index, 1001)
    index["files"]["azure/functions/japaneast.json"]["writer"] = "2.3.13"     # as an older version left it
    (tmp_path / "index.json").write_text(json.dumps(index))
    answers.pop(AZ.query_url("Functions", "japaneast"))
    index = F.run(azure_only(), tmp_path, at_ms=2000, get=fake_get(answers), provider="azure")
    assert index["files"]["azure/functions/japaneast.json"]["writer"] == "2.3.13"
    assert index["files"]["azure/key-vault/japaneast.json"]["writer"] == F.WRITER
    # the price book reads every file this version wrote and not the one it did not: the bundled price stands in
    rows, why = pricebook.cache_rows(tmp_path)
    assert {r["file"] for r in rows} == {k for k in index["files"] if k != "azure/functions/japaneast.json"
                                         and index["files"][k].get("fetchedAt")}
    assert why == ["1 fetched price file(s) were written by another jsonui-cli version (or the index does not name "
                   f"them): not used until fetched again by {F.WRITER}; the bundled prices stand in"]


def test_a_file_another_version_wrote_is_not_read_and_the_bundled_price_stands_in(tmp_path):
    """The ticket's case: the cache holds 2.3.13's egress row (no free amount) for us-east-1. Read by this version, the
    row is not used and the bundled row (with the account's 100 GB a month) prices it; written by this version, the
    cache's row is used."""
    from jsonui_doc_cli.infra.cost import pricebook as PB
    folder = tmp_path / "cloud-prices"
    (folder / "aws" / "awsdatatransfer").mkdir(parents=True)
    old_row = {"provider": "aws", "service": "data-transfer", "sku": "egress", "region": "us-east-1", "unit": "GB",
               "price_usd": 0.09, "effective": "2026-10-01", "source": "https://pricing.us-east-1.amazonaws.com/x"}
    (folder / "aws" / "awsdatatransfer" / "us-east-1.json").write_text(json.dumps({"version": 0, "prices": [old_row]}))
    rel = "aws/awsdatatransfer/us-east-1.json"
    for writer, layer in ((None, "bundled"), ("2.3.13", "bundled"), (F.WRITER, "cache")):
        entry = {"fetchedAt": 1} | ({"writer": writer} if writer else {})
        (folder / "index.json").write_text(json.dumps({"version": 1, "files": {rel: entry}}))
        rows, why = PB.cache_rows(folder)
        book = PB.Book(cache=rows, bundled=PB.bundled_rows())
        found = book.find("aws", "data-transfer", "egress", "GB", "us-east-1", "2026-11-01")
        assert found["layer"] == layer, (writer, found)
        if layer == "bundled":
            assert found["row"].get("free", {}).get("pool") == "aws:data-transfer-out" and rows == []
            assert why and "written by another jsonui-cli version" in why[0]
        else:
            assert "free" not in found["row"] and why == []


# ---------------------------------------------------------------- the real get, its answer replaced (nothing outside)

class FakeResp:
    def __init__(self, url, body=b"", lines=()):
        self.url, self.body, self.lines = url, body, list(lines)

    def geturl(self):
        return self.url

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __iter__(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """Stands for the opener: answers every request with one response."""

    def __init__(self, make):
        self.make = make

    def open(self, req, timeout=None):
        return self.make(req, timeout)


def test_a_redirect_away_from_the_price_hosts_is_refused_before_it_is_followed(monkeypatch):
    """The opener's own lower layer is replaced: the price host answers 302 to another host; that host's handler must
    never be called (the check is on the Location, before the request — not on where the answer came from)."""
    import email.message
    import io
    import urllib.response
    url = AZ.query_url("Functions", "japaneast")
    asked = []

    def answer(req, code, location=None):
        h = email.message.Message()
        if location:
            h["Location"] = location
        resp = urllib.response.addinfourl(io.BytesIO(b"{}"), h, req.full_url, code=code)
        resp.msg = "Found" if code == 302 else "OK"
        return resp

    class Lower(urllib.request.BaseHandler):
        handler_order = 100

        def https_open(self, req):
            asked.append(req.full_url)
            if req.host == "prices.azure.com" and "moved" not in req.full_url:
                return answer(req, 302, self.location)
            return answer(req, 200)

        def http_open(self, req):
            asked.append(req.full_url)
            return answer(req, 200)

    real = F._opener
    monkeypatch.setattr(F, "_opener", lambda: real(Lower))   # the real opener, its lower layer replaced
    for away in ("https://evil.example/x", "http://prices.azure.com/api/retail/prices", "https://prices.azure.com:8443/x"):
        Lower.location, asked[:] = away, []
        with pytest.raises(F.Refused):
            F.http_get(url, 1000)
        assert asked == [url], (away, asked)   # the second host was never asked
    Lower.location, asked[:] = "https://prices.azure.com/api/retail/prices?moved=1", []
    assert F.http_get(url, 1000) == b"{}" and len(asked) == 2   # a redirect within the rules is followed


def test_where_the_answer_came_from_is_checked_too(monkeypatch):
    url = AZ.query_url("Functions", "japaneast")
    monkeypatch.setattr(F, "_opener", lambda: FakeOpener(lambda req, timeout: FakeResp("https://evil.example/x", b"{}")))
    with pytest.raises(F.Refused):
        F.http_get(url, 1000)
    monkeypatch.setattr(F, "_opener", lambda: FakeOpener(lambda req, timeout: FakeResp(url, b"{}")))
    assert F.http_get(url, 1000) == b"{}"


def test_only_a_user_agent_is_sent(monkeypatch):
    seen = {}
    def opener(req, timeout):
        seen["headers"], seen["timeout"] = dict(req.header_items()), timeout
        return FakeResp(req.full_url, b"{}")
    monkeypatch.setattr(F, "_opener", lambda: FakeOpener(opener))
    F.http_get(AZ.query_url("Functions", "japaneast"), 1000)
    assert seen["headers"] == {"User-agent": "jui-viz"} and seen["timeout"] == F.TIMEOUT_SEC


def test_the_size_cap_of_an_answer_and_of_a_stream(monkeypatch):
    url = AWS.OFFER_URL.format(offer="AWSLambda", region="ap-northeast-1")
    monkeypatch.setattr(F, "_opener", lambda: FakeOpener(lambda req, timeout: FakeResp(url, b"x" * 101)))
    with pytest.raises(F.Refused):
        F.http_get(url, 100)
    assert F.http_get(url, 101) == b"x" * 101
    csv_url = AWS.EC2_CSV_URL.format(region="ap-northeast-1")
    monkeypatch.setattr(F, "_opener", lambda: FakeOpener(lambda req, timeout: FakeResp(csv_url, lines=[b"a" * 60 + b"\n"] * 2)))
    with pytest.raises(F.Refused):
        list(F.http_lines(csv_url, 100))
    assert len(list(F.http_lines(csv_url, 122))) == 2
