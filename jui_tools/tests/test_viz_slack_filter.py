"""The Slack intake's builtin filter (design 2026-11-02 §1, §4): one arm per key shape, a positive and a negative.

The sample secrets are written split and joined here (a whole one in the source would stop a push).
A positive: the shape is replaced by [REDACTED:<kind>] and counted. A negative: a look-alike that is no secret
stays as written (a filter that masks everything would pass every positive and still ruin the routing).
"""
from __future__ import annotations

import pytest

from jui_cli.viz.slack import filters as F

J = "".join

POSITIVE = [
    ("slack-token", J(["xox", "b-1234567890-", "abcdefghijKLMN"])),
    ("slack-token", J(["xox", "p-11111-22222-", "abcdef123456"])),
    ("slack-app-token", J(["xa", "pp-1-A0123-", "4567890abcdef"])),
    ("slack-webhook", J(["https://hooks.slack", ".com/services/T000/B000/", "XXXXyyyyZZZZ"])),
    ("aws-access-key", J(["AK", "IA", "IOSFODNN7EXAMPLE"])),
    ("aws-access-key", J(["AS", "IA", "Y34EXAMPLE7ABCDE"])),
    ("aws-secret-key", "aws_secret_access_key = " + J(["wJalrXUtnFEMI/K7MDENG/", "bPxRfiCYEXAMPLEKEY"])),
    ("github-token", J(["gh", "p_", "a" * 36])),
    ("github-token", J(["github", "_pat_", "11ABCDEFG0", "abcdefghijklmnopqrstuv"])),
    ("anthropic-key", J(["sk", "-ant-", "api03-", "abcdefghijklmnopqrstuvwxyz"])),
    ("openai-key", J(["sk", "-proj-", "abcdefghijklmnopqrstuvwx"])),
    ("google-api-key", J(["AI", "za", "SyA1234567890abcdefghijklmnopqrstuv"])),
    ("jwt", J(["ey", "JhbGciOiJIUzI1NiJ9", ".ey", "JzdWIiOiIxMjM0NTY3ODkwIn0", ".abcdefghijk"])),
    ("private-key", J(["-----BEGIN ", "RSA PRIVATE KEY-----\nMIIEow\nAAAA\n-----END ", "RSA PRIVATE KEY-----"])),
    ("private-key", J(["-----BEGIN ", "OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk\n(cut off)"])),
    ("password", "password: hunter22"),
    ("password", "パスワードは Abc12345"),
    ("password", "token=abcd1234efgh"),
    ("password", "暗証番号：1234"),
    ("password", "パスコード＝abcd"),
    ("email", "taro.yamada@example.co.jp"),
    ("email", "<mailto:a.b@example.com|a.b@example.com>"),
    ("phone", "03-1234-5678"),
    ("phone", "09012345678"),
    ("phone", "+81 90-1234-5678"),
]

NEGATIVE = [
    "sk-short",                                   # an sk- too short to be a key
    "AKIA1234",                                   # an AKIA too short
    "xoxb",                                       # the prefix alone
    "1730000000.123456",                          # a Slack ts
    "2026-11-02 の 09:00 に",                     # a date and a time
    "v10.31.0 と 2.3.38 を配布",                   # versions
    "注文番号 12-3456",                            # a number with a hyphen
    "パスワードは忘れずに変えてね",                  # the word without a value
    "password policy を決める",                    # the word in a sentence
    "token: 3",                                   # a value too short
    "<@U012ABCDE> <#C0123ABCD|general> @channel",  # mentions and a channel
    "https://example.com/path?q=1",               # a plain URL
    "ghp_ と打つと GitHub のトークン",               # the prefix alone
    "-----BEGIN CERTIFICATE-----",                # a certificate, not a private key
]


@pytest.mark.parametrize("kind,secret", POSITIVE, ids=[f"{k}-{i}" for i, (k, _s) in enumerate(POSITIVE)])
def test_each_key_shape_is_masked_and_counted(kind, secret):
    text, n = F.redact(f"前の文 {secret} 後の文", F.compile_patterns([]))
    assert f"[REDACTED:{kind}]" in text, text
    assert n >= 1
    core = secret.split("=")[-1].split(":")[-1].strip().split("|")[0].lstrip("<mailto")
    assert core not in text, text
    assert text.startswith("前の文 ") and text.endswith(" 後の文") or kind == "private-key"


@pytest.mark.parametrize("text", NEGATIVE)
def test_a_look_alike_is_left_as_written(text):
    got, n = F.redact(text, F.compile_patterns([]))
    assert (got, n) == (text, 0)


def test_a_value_already_masked_is_not_counted_twice():
    token = J(["xox", "b-1234567890-", "abcdefghijKLMN"])
    got, n = F.redact(f"token: {token}", F.compile_patterns([]))
    assert got == "token: [REDACTED:slack-token]" and n == 1


def test_extra_patterns_from_the_config_mask_too_and_a_broken_one_is_a_filter_error():
    compiled = F.compile_patterns(["ACME-\\d{6}", {"name": "employee", "pattern": "EMP\\d{4}"}])
    got, n = F.redact("ACME-123456 と EMP0042", compiled)
    assert got == "[REDACTED:extra-1] と [REDACTED:employee]" and n == 2
    with pytest.raises(F.FilterError):
        F.compile_patterns(["(unclosed"])
    with pytest.raises(F.FilterError):
        F.compile_patterns([42])


def test_the_builtin_adapter_drops_the_files_and_gives_the_contract_fields_only():
    record = {"workspace": "acme", "channel": "C0123", "ts": "1730000000.000100", "permalink": "https://x/p1",
              "via": "api", "message": {"type": "message", "user": "U1", "ts": "1730000000.000100",
                                        "text": "見積もりです " + J(["AK", "IA", "IOSFODNN7EXAMPLE"]),
                                        "files": [{"name": "見積.pdf", "url_private": "https://files.slack.com/x"},
                                                  {"name": "b.png"}],
                                        "attachments": [{"text": "unfurled body"}],
                                        "blocks": [{"type": "rich_text"}]}}
    got = F.apply(record, {"adapter": "builtin", "extraPatterns": []})
    assert set(got) == {"workspace", "channel", "user", "ts", "threadTs", "replyCount", "text", "permalink",
                        "removedFiles", "redactions"}
    assert got["threadTs"] == "1730000000.000100" and got["replyCount"] == 0
    assert got["removedFiles"] == 2 and got["redactions"] == 1
    assert got["text"] == "見積もりです [REDACTED:aws-access-key]"
    flat = repr(got)
    for gone in ("見積.pdf", "files.slack.com", "unfurled body", "rich_text", "IOSFODNN7EXAMPLE"):
        assert gone not in flat
