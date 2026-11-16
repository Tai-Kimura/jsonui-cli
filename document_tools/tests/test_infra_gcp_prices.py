"""Google Cloud's prices from the Cloud Billing Catalog API (cost/gcp_prices.py): the key read from one environment
variable only and never written anywhere, and the rows read from the SKUs as the API answers them.

The answers here are written in the catalog's shape (services: displayName / serviceId; skus: description, category,
serviceRegions, pricingInfo[].pricingExpression.tieredRates with units + nanos), not copied from it.
"""
from __future__ import annotations

import ast
import io
import json
import urllib.error
from pathlib import Path

import pytest

from jsonui_doc_cli.infra.cost import gcp_prices as G

KEY = "AIza" + "FakeKeyForTheArms0123456789abcdef"    # written split: a key's shape never sits whole in a file


def sku(description, region, units, nanos, unit="h", start=0, family="Compute", group="CPU", usage="OnDemand",
        more_tiers=()):
    rates = [{"startUsageAmount": start, "unitPrice": {"currencyCode": "USD", "units": str(units), "nanos": nanos}}]
    rates += [{"startUsageAmount": s, "unitPrice": {"currencyCode": "USD", "units": str(u), "nanos": n}}
              for s, u, n in more_tiers]
    return {"skuId": description[:8], "description": description,
            "category": {"serviceDisplayName": "Cloud Run", "resourceFamily": family, "resourceGroup": group,
                         "usageType": usage},
            "serviceRegions": [region],
            "pricingInfo": [{"effectiveTime": "2026-10-01T00:00:00Z",
                             "pricingExpression": {"usageUnit": unit, "tieredRates": rates}}]}


SPEC = [G.G("Cloud Run", r"^CPU Allocation Time \(tier 1\)$", "run", "vcpu", "vCPU-hour", "s", scale=3600),
        G.G("Cloud Run", r"^Requests$", "run", "requests", "request", "count", per_units=1_000_000)]


def test_rows_from_the_catalogs_shape():
    skus = [sku("CPU Allocation Time (tier 1)", "asia-northeast1", 0, 24000, unit="s",
                more_tiers=[(180000, 0, 24000)]),
            sku("CPU Allocation Time (tier 1)", "asia-northeast1", 0, 18000, unit="s", usage="Commit1Yr"),
            sku("Requests", "asia-northeast1", 0, 400, unit="count", more_tiers=[(2_000_000, 0, 400)]),
            sku("Requests", "us-east1", 0, 999, unit="count")]
    rows, missing = G.rows_from_skus(skus, "152E-C115-5142", "Cloud Run", "asia-northeast1", SPEC)
    assert missing == []
    vcpu, req = rows
    # a vCPU-second at $0.000024 is $0.0864 a vCPU-hour; the first 180,000 seconds are 50 hours
    assert (vcpu["sku"], vcpu["unit"], vcpu["tiers"]) == ("vcpu", "vCPU-hour", [
        {"from": 0.0, "price_usd": 0.0864, "to": 50.0}, {"from": 50.0, "price_usd": 0.0864}])
    assert req["per_units"] == 1_000_000 and req["tiers"][1] == {"from": 2_000_000.0, "price_usd": 0.4}
    assert vcpu["source"] == "https://cloudbilling.googleapis.com/v1/services/152E-C115-5142/skus"
    assert vcpu["effective"] == "2026-10-01" and vcpu["region"] == "asia-northeast1"


def test_a_sku_in_another_unit_or_none_is_said_not_guessed():
    skus = [sku("CPU Allocation Time (tier 1)", "asia-northeast1", 0, 24000, unit="h")]
    rows, missing = G.rows_from_skus(skus, "x", "Cloud Run", "asia-northeast1", SPEC)
    assert rows == [] and len(missing) == 2
    assert "usageUnit 'h' is not 's'" in missing[0] and "no sku" in missing[1]


def test_the_key_is_read_from_its_environment_variable_only():
    assert G.api_key({G.KEY_ENV: f"  {KEY}\n"}) == KEY
    assert G.api_key({}) is None and G.api_key({G.KEY_ENV: "  "}) is None
    # the code, its docstrings left out (they name what it does not read): no other place a key could come from
    tree = ast.parse(Path(G.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body.pop(0)
    code = ast.unparse(tree).lower()
    for other in ("keychain", "keyring", "subprocess", "gcloud", "expanduser", "home()", "getpass", ".config"):
        assert other not in code, other
    assert code.count("environ") >= 1 and "os.environ if environ is none else environ" in code


def test_no_key_downloads_nothing_and_says_so(tmp_path):
    said = []
    assert G.download(tmp_path, environ={}, opener=lambda *a, **k: pytest.fail("no request without a key"),
                      log=said.append) == 0
    assert said == [G.NO_KEY] and not (tmp_path / "gcp").exists()
    rows, missing, why = G.rows_from_folder(tmp_path)
    assert rows == [] and missing == [] and G.KEY_ENV in why


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_key_travels_in_a_header_and_is_written_nowhere(tmp_path):
    seen = []

    def opener(req, timeout):
        seen.append(req)
        url = req.full_url
        if url.startswith(f"{G.API}/services?"):
            return _Answer(json.dumps({"services": [{"displayName": "Cloud Run", "serviceId": "152E"}]}).encode())
        return _Answer(json.dumps({"skus": [sku("Requests", "asia-northeast1", 0, 400, unit="count")]}).encode())
    said = []
    assert G.download(tmp_path, environ={G.KEY_ENV: KEY}, opener=opener, services=("Cloud Run",),
                      log=said.append) == 0
    assert [r.get_header("X-goog-api-key") for r in seen] == [KEY, KEY]
    assert all(KEY not in r.full_url for r in seen)
    written = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "gcp").iterdir())
    assert KEY not in written and KEY not in "".join(said)
    assert (tmp_path / "gcp" / "152E.json").is_file()


@pytest.mark.parametrize("failure", ["http", "other"])
def test_a_failure_says_why_without_the_key(tmp_path, failure):
    def opener(req, timeout):
        if failure == "http":   # an answer that echoes what it was sent
            raise urllib.error.HTTPError(req.full_url + f"&key={KEY}", 403, f"API key {KEY} not valid",
                                         {"X-Goog-Api-Key": KEY}, io.BytesIO(KEY.encode()))
        raise OSError(f"connection reset while sending header X-Goog-Api-Key: {KEY}")
    said = []
    assert G.download(tmp_path, environ={G.KEY_ENV: KEY}, opener=opener, log=said.append) == 1
    assert said and all(KEY not in s for s in said) and "***" in said[-1]
    with pytest.raises(G.FetchError) as e:
        G._get(f"{G.API}/services?pageSize=1", KEY, opener)
    assert KEY not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__


def test_redact_takes_out_the_key_as_written_and_as_quoted():
    assert G.redact(f"a {KEY} b", KEY) == "a *** b"
    assert G.redact("k=" + "AIza%2B" + KEY[4:], "AIza+" + KEY[4:]) == "k=***"   # quoted in a URL
    assert G.redact("nothing", None) == "nothing"


def test_the_table_is_built_without_gcp_when_no_key_was_given(tmp_path, monkeypatch):
    """build_bundled reads what was downloaded and never the key: with no <folder>/gcp it makes the rest and says
    why GCP is missing — a notice, not a gap (the exit code stays the rest's)."""
    from jsonui_doc_cli.infra.cost import azure_prices as AZ
    from jsonui_doc_cli.infra.cost import build_bundled as BB
    monkeypatch.setattr(BB, "aws_rows", lambda folder: ([], []))
    monkeypatch.setattr(AZ, "rows_from_folder", lambda folder: ([], []))
    monkeypatch.setenv(G.KEY_ENV, KEY)        # set, and still not read here
    notices: list[str] = []
    doc, missing = BB.build(tmp_path, "2026-10-20", notices=notices)
    assert missing == [] and not any(r["provider"] == "gcp" for r in doc["prices"])
    assert len(notices) == 1 and G.KEY_ENV in notices[0] and KEY not in json.dumps(doc) + notices[0]


# ---------------------------------------------------------------- redirects (ticket 2026-10-21-gcp-billing-key-follows-
# redirects): urllib carries a request's own headers to where a redirect points, the key among them

class _Net(urllib.request.BaseHandler):
    """The network, for the arms: the Catalog API answers a redirect to ``to``; every other host answers 200 and
    is recorded with the headers it was sent. Ahead of urllib's own HTTPS handler: nothing reaches the network."""
    handler_order = 100

    def __init__(self, to):
        self.to, self.reached = to, []

    def https_open(self, req):
        import email.message
        import urllib.response
        host = urllib.parse.urlsplit(req.full_url).hostname
        msg = email.message.Message()
        if host == "cloudbilling.googleapis.com" and not self.reached and "pageToken" not in req.full_url:
            msg["Location"] = self.to
            resp = urllib.response.addinfourl(io.BytesIO(b""), msg, req.full_url, 302)
            resp.msg = "Found"
            return resp
        self.reached.append((host, dict(req.header_items())))
        resp = urllib.response.addinfourl(io.BytesIO(b'{"services": []}'), msg, req.full_url, 200)
        resp.msg = "OK"
        return resp


@pytest.mark.parametrize("to", ["https://elsewhere.example/v1/services", "http://cloudbilling.googleapis.com/v1/x",
                                "https://cloudbilling.googleapis.com:8443/v1/x",
                                "https://cloudbilling.googleapis.com/v1/services?pageSize=1"])
def test_no_redirect_is_followed_so_the_key_goes_nowhere_else(tmp_path, to):
    """Another host, scheme or port — and the Catalog API itself: a redirect is a failure, not followed. The key is
    sent once, to the URL asked, and the failure's words do not hold it."""
    net = _Net(to)
    said = []
    assert G.download(tmp_path, environ={G.KEY_ENV: KEY}, opener=G.opener_with(net), log=said.append) == 1
    assert net.reached == []
    assert len(said) == 1 and "a redirect to" in said[0] and "not followed" in said[0] and KEY not in said[0]


def test_a_url_that_is_not_the_catalog_api_is_not_asked():
    net = _Net("https://elsewhere.example/")
    with pytest.raises(G.FetchError) as e:
        G._get("https://elsewhere.example/v1/services", KEY, G.opener_with(net))
    assert net.reached == [] and KEY not in str(e.value) and "not the Catalog API" in str(e.value)


def test_the_catalog_api_answering_is_read_with_the_key_in_its_header():
    net = _Net("unused")
    net.reached.append(("primed", {}))     # the first answer is 200, not a redirect
    assert G._get(f"{G.API}/services?pageSize=1", KEY, G.opener_with(net)) == {"services": []}
    host, headers = net.reached[1]
    assert host == "cloudbilling.googleapis.com" and headers["X-goog-api-key"] == KEY


def test_azure_download_stays_on_prices_azure_com(tmp_path):
    """Azure's answers are public (no key), and still: a redirect off prices.azure.com is refused (L-B2's rule)."""
    from jsonui_doc_cli.infra.cost import azure_prices as AZ

    class AzNet(_Net):
        def https_open(self, req):
            import email.message
            import urllib.response
            host = urllib.parse.urlsplit(req.full_url).hostname
            if host == "prices.azure.com":
                msg = email.message.Message()
                msg["Location"] = self.to
                resp = urllib.response.addinfourl(io.BytesIO(b""), msg, req.full_url, 302)
                resp.msg = "Found"
                return resp
            return super().https_open(req)
    from jsonui_doc_cli.infra.cost import fetch as FETCH
    net = AzNet("https://elsewhere.example/api")
    said = []
    assert AZ.download(tmp_path, spec=AZ.SPEC[:1], opener=FETCH._opener(net).open, log=said.append) == 1
    assert net.reached == [] and "not fetched" in said[0]


def test_the_default_opener_refuses_redirects_too(monkeypatch):
    """No opener given: the one the download builds — urllib's own HTTPS handler answering a redirect, stood in for
    so nothing reaches the network — still follows none."""
    net = _Net("https://elsewhere.example/v1/services")
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", lambda self, req: net.https_open(req))
    with pytest.raises(G.FetchError) as e:
        G._get(f"{G.API}/services?pageSize=1", KEY)
    assert net.reached == [] and "not followed" in str(e.value) and KEY not in str(e.value)


def test_azure_asks_only_prices_azure_com(tmp_path, monkeypatch):
    """The first request too: a query URL not on prices.azure.com over https is refused before it is sent."""
    from jsonui_doc_cli.infra.cost import azure_prices as AZ
    net = _Net("unused")
    net.reached.append(("primed", {}))
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", lambda self, req: net.https_open(req))
    monkeypatch.setattr(AZ, "API", "https://elsewhere.example/api/retail/prices")
    said = []
    assert AZ.download(tmp_path, spec=AZ.SPEC[:1], log=said.append) == 1
    assert net.reached == [("primed", {})] and "not fetched" in said[0]


def test_azures_default_opener_refuses_a_redirect_off_its_host(tmp_path, monkeypatch):
    from jsonui_doc_cli.infra.cost import azure_prices as AZ
    reached = []

    def https_open(self, req):
        import email.message
        import urllib.response
        host = urllib.parse.urlsplit(req.full_url).hostname
        msg = email.message.Message()
        if host == "prices.azure.com":
            msg["Location"] = "https://elsewhere.example/api"
            resp = urllib.response.addinfourl(io.BytesIO(b""), msg, req.full_url, 302)
            resp.msg = "Found"
            return resp
        reached.append(host)
        resp = urllib.response.addinfourl(io.BytesIO(b'{"Items": []}'), msg, req.full_url, 200)
        resp.msg = "OK"
        return resp
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", https_open)
    said = []
    assert AZ.download(tmp_path, spec=AZ.SPEC[:1], log=said.append) == 1
    assert reached == [] and "not fetched" in said[0]
