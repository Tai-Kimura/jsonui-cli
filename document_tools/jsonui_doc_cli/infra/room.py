"""A room's declared infrastructure, read the one way the boundary allows (§2, §5.2 of
docs/plans/2026-10-20-jui-viz-server-room-boundary.md): where (jui.config.json's ``infra``), which files, how (from the
room's real root one part at a time with O_NOFOLLOW, the file itself O_NONBLOCK and fstat'ed as a regular file), how
much (LIMITS), and what goes wrong (a reason code). ``validate infra`` reads with it; jui viz may too.

The client never names a path: everything is under the room's root, chosen here. Self-contained (json, os, pathlib).
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path, PurePosixPath

from . import model as M

DEFAULT_DIR = "docs/infra"
CONFIG_NAME = "jui.config.json"
LIMITS = {"files": 50, "file_bytes": 4_000_000, "total_bytes": 16_000_000, "icons": 64, "icon_bytes": 256_000,
          "config_bytes": 1_000_000}
ICON_KEY = re.compile(r"^(?:service:[a-z0-9][a-z0-9.-]{0,39}/[a-z0-9][a-z0-9._/-]{0,63}"
                      r"|provider:[a-z0-9][a-z0-9.-]{0,39}|category:[a-z0-9][a-z0-9._]{0,39})$")
ICON_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp"}
REASONS = {"not_a_room": 404, "no_infra": 404, "bad_config": 400, "too_many_files": 413, "too_large": 413,
           "invalid": 422, "unreadable": 500}
SECRET_JA = {"arn": "ARN", "account_id": "アカウント ID", "ip_address": "IP アドレス", "connection_string": "接続文字列",
             "url_credentials": "URL の中の資格情報", "private_key": "秘密鍵", "access_key": "アクセスキー", "token": "トークン",
             "password": "パスワード"}   # one per model.SECRET_KINDS (test_infra_room: a kind with no words is red)

#: one per problem code flows.py gives (test_infra_flows: a code with no words is red)
FLOW_JA = {"flow.node.missing": "が、この flow と一緒に描かれない node を指しています",
           "flow.edge.missing": "が通る辺がありません",
           "flow.discontinuous": "が、今いる node から出ていません（往復は request と response の 2 ステップ・エラーで終わる選択肢は join・並びは今いる node から）",
           "flow.step.kind": "の step の書き方が 1 つに決まりません（辺・node・分かれ道・並びのどれか 1 つ）",
           "flow.paths_disagree": "の step に、道によって違う node から着きます（エラーで終わる選択肢は join で終わりの step へ）",
           "flow.too_deep": "の分かれ道と並びの入れ子が深すぎます",
           "flow.choice.duplicate": "の分かれ道に、同じ id の選択肢があります",
           "flow.choice.kind": "の選択肢の進み方が 1 つに決まりません（steps・goto・join のどれか）",
           "flow.default.missing": "の既定が、どの選択肢も指していません",
           "flow.join.missing": "の join が、この flow の step を指していません",
           "flow.join.backward": "の join が、分かれ道より前の step を指しています",
           "flow.goto.missing": "の goto が、描かれない flow を指しています",
           "flow.goto.jump": "の goto の先は、別の node から始まります（画面では跳びます）",
           "flow.default_cycle": "は、既定だけで輪になり、ひとりでに流すと終わりません",
           "flow.env.partial": "の道筋が、そろわない環境があります（環境ごとに、通る node と辺が全部描かれていること）",
           "flow.id.duplicate": "の id が、ほかの flow と重なっています",
           "flow.schedule.trigger": "の schedule は、trigger が schedule の時だけ書けます"}

#: one per keyword model.check_schema says (a schema problem's detail; test_infra_room: a keyword with no words is red).
#: The slots are the detail's: the limit, the length or count found, the type found, what is allowed — never the value
SCHEMA_JA = {"maxLength": "は {limit} 文字までです（今 {length} 文字）",
             "minLength": "は {limit} 文字以上です（今 {length} 文字）",
             "pattern": "の形が違います（書ける形: {pattern}）",
             "enum": "は {allowed} のどれかです",
             "const": "は {allowed} です",
             "type": "は{want}です（今は{found}）",
             "oneOf": "が {n} 通りの形のうち {fit} 通りに合います（1 つだけに合うこと）",
             "required": "がありません（書かなければならない欄です）",
             "additionalProperties": "は書けない欄です（ここに書ける欄: {fields}）",
             "minimum": "は {limit} 以上です（今の値は {limit} より小さい）",
             "maximum": "は {limit} 以下です（今の値は {limit} より大きい）",
             "exclusiveMinimum": "は {limit} より大きい数です（今の値は {limit} 以下）",
             "finite": "は有限の数です（NaN・Infinity は書けません）",
             "minItems": "は {limit} 個以上です（今 {count} 個）",
             "maxItems": "は {limit} 個までです（今 {count} 個）",
             "uniqueItems": "に同じ物が 2 度あります（{first} 番目と {second} 番目、0 から数えて）",
             "propertyNames": "の名前の形が違います（書ける形: {pattern}）",
             "minProperties": "は {limit} 項目以上です（今 {count} 項目）",
             "maxProperties": "は {limit} 項目までです（今 {count} 項目）"}

#: one per words key a load definition's or a price file's problem says (load.py, prices.py: a problem's detail; the
#: test_infra_side_words gate: a key with no words, or words no problem says, is red). The slots are the detail's
SIDE_JA = {"load.timezone": "は、この機械が知らない timezone です",
           "load.date.calendar": "は、暦にある日付ではありません",
           "load.date.month": "は、{month} の月の日付ではありません",
           "load.date.twice": "は、days に 2 度ある日付です",
           "load.ref": "が、このファイルに無い {what} を指しています",
           "load.rule": "の rule は、始まる時刻か、それより前に終わります（日をまたぐ rule は 2 つに分けてください）",
           "load.minmax": "の min が max より大きいです",
           "load.minmax.rule": "の min が、schedule の rule {j} の時間では max より大きいです",
           "load.minmax.step": "の min の step が、max の step より上です",
           "load.autoscale.per_instance": "に per_instance がありません（書かずに済むのは vertical の時だけです。その step が 1 台の受け持ちを言います）",
           "load.autoscale.vertical": "は、vertical がある時は vertical の quantity でなければなりません",
           "load.flow_unwritten": "が、この行の書く flow の量を指していません",
           "load.ladder.duplicate": "に、同じ sku が 2 度あります",
           "load.ladder.amount": "は、amount も vcpu・memory_gb も言っていません",
           "load.ladder.grow": "は、1 つ前の step より大きくありません",
           "load.ladder.not_step": "は、ladder の step ではありません",
           "load.ladder.quantity": "の step が amount を言うので、quantity が要ります",
           "load.ladder.rule": "の schedule の rule {j} が、ladder に無い sku を指しています",
           "load.target.node": "には、node と nodes のどちらか 1 つが要ります",
           "load.target.edge": "には、辺の id か、from と to の両方が要ります",
           "load.environment.none": "が書かれておらず、モデルに環境が {n} 個あります（最初の環境を使います）",
           "load.environment.unknown": "は、モデルの環境ではありません（最初の環境を使います）",
           "load.node_missing": "が、モデルに無い node を指しています（この行は使いません）",
           "load.not_in_environment": "の node は、この scenario の環境にありません（この行は使いません）",
           "load.select_none": "は、環境のどの node にも当たりません",
           "load.overlap.own": "の node には、自分の行 {row} があります（そちらを使います。1 つの node に効く行は 1 つで、node 自身の行が selector の行に勝ちます）",
           "load.overlap.later": "の node には、もう行 {row} があります（後のこの行を使い、行 {row} は数えません。1 つの node に効く行は 1 つです。node の量は 1 行にまとめてください）",
           "load.sku.multi_az": "の sku {sku} は :multi-az 付きです（素の sku を書き、node に ha: multi-az と書いてください。費用は ha から instance と storage に :multi-az を足します。手で書くと storage は single-AZ のままです）",
           "load.quantity_unused": "は、{category} の node が読まない量です（{rule}）",
           "load.schedule_unused": "は、時間で課金されない {category} の node では何も変えません（{rule}）",
           "load.edge_missing": "が、この環境のモデルに無い辺を指しています（この行は使いません）",
           "load.edge_ambiguous": "の node の間に、辺が {n} 本あります（最初の 1 本を使います。辺は id で指してください）",
           "load.while_stopped": "で、node が 0 台の {n} 時間に {flows} が流れます（最初は {date} {hour}:00）",
           "load.id.duplicate": "の scenario の id は、{file} でもう使われています",
           "prices.row.exactly_one": "には、price_usd と tiers のどちらか 1 つが要ります（この行は使いません）",
           "prices.row.effective": "の effective は、暦にある日付ではありません（この行は使いません）",
           "prices.row.tier_start": "の最初の tier が 0 から始まりません（この行は使いません）",
           "prices.row.tier_end": "の tier {k} は、始まる所か、それより前で終わります（この行は使いません）",
           "prices.row.tier_open": "の tier {k} は、終わりが無いのに最後ではありません（この行は使いません）",
           "prices.row.tier_gap": "の tier {next} が、tier {k} の終わる所から始まりません（この行は使いません）",
           "prices.duplicate": "は、行 {row} と同じ価格です（先の行を使います）"}

#: one per words key the cost simulator says on its own (engine.py's warnings, a rule's notice in rules/, the price
#: book's warnings in cost/pricebook.py; test_infra_side_words: closed both ways). A line names no value found: a
#: rule's failure says its exception's type only. An empty service or region: COST_EMPTY_JA
COST_JA = {"cost.rule_failed": "rule {rule} が失敗しました（{error}）",
           "cost.no_price": "{service} {sku}（{unit}）の価格が、{region} にありません",
           "cost.no_price.transfer": "data-transfer {sku} の価格が、{region} にありません",
           "cost.free_per_scenario": "無料枠は scenario ごとに 1 回差し引きます。scenario は 1 つの環境なので、1 つのアカウントを分け合う環境（1 つの AWS アカウントの production と staging）は、それぞれがアカウントの無料枠を取り、合計はその分だけ低く出ます。1 回だけ取るには、アカウントとして見積もってください（simulate_account: scenario をまとめて 1 つの合計にします）",
           "cost.account_other_month": "{first} ではなく {month} の scenario です。単独で見積もり、無料枠はアカウントのものを使いません",
           "cost.stepfunctions_no_transitions": "Standard の workflow は state transition ごとに課金されます。load に requests があって state_transitions が無いので、0 と見積もります（state_transitions を書くか、spec に workflow_type: express と書いてください）",
           "cost.apprunner_active_upper_bound": "requests のある時間は、その 1 時間ずっと動いていると数えます（vCPU とメモリ）。App Runner は requests を処理した秒だけ課金するので、これは上限です",
           "cost.waf_kind.said": "WAF を {kind} の WAF として見積もります（node の spec がそう言っています）",
           "cost.waf_kind.default": "WAF を Application Gateway WAF v2 として見積もります（node が種類を言っていません。Front Door の policy なら、spec に kind: frontdoor と書いてください）",
           "cost.free_not_counted.run": "Cloud Run の月ごとの無料の vCPU 秒と GiB 秒（請求先アカウントごと）は、差し引いていません。Cloud Billing Catalog に載っておらず、そのページも読めなかったためです。vCPU とメモリは最初の 1 秒から見積もります（無料の 200 万 requests は数えています）",
           "cost.free_not_counted.gke": "GKE のクラスタ管理料の月ごとの無料クレジット（請求先アカウントごと）は、差し引いていません。管理料は最初の 1 時間から見積もります",
           "prices.cache_unused": "取ってきた価格のファイル {file} は使いません（{code}）",
           "prices.cache_other_version": "取ってきた価格のファイル {n} 個は、別の版の jsonui-cli が書いたか、索引に名前がありません。{writer} がもう一度取ってくるまで使わず、同梱の価格を使います",
           "prices.free_dropped": "{file} /prices/{index}: {price} には無料枠がありませんが、同梱の価格は 1 か月に {amount} {unit} を無料にします。この行が勝つので、無料枠は取りません（残すには、この行に free を書いてください）",
           "prices.free_dropped.pool": "{file} /prices/{index}: {price} には無料枠がありませんが、同梱の価格は、アカウントの枠 {pool} から 1 か月に {amount} {unit} を無料にします。この行が勝つので、無料枠は取りません（残すには、この行に free を書いてください）",
           "prices.room_unused": "部屋の価格のファイルを使いません（{reason}）: {line}"}

#: an empty value in a cost line (COST_JA)
COST_EMPTY_JA = {"service": "（service 無し）", "region": "（region 無し）"}


#: a JSON type's name, in a type line (SCHEMA_JA["type"])
TYPE_JA = {"object": "オブジェクト", "array": "配列", "string": "文字列", "integer": "整数", "number": "数",
           "boolean": "真偽値（true・false）", "null": "null"}

#: one per problem code a migration plan gives (migration.CODES; test_infra_migration: a code with no words is red)
MIGRATION_JA = {"migration.remove_missing": "で消すものが、旧の構成にありません",
                "migration.duplicate": "に、同じものが 2 度書かれています（先の物を使います）",
                "migration.both": "のものが、changes にも書かれています（消さずに差し替えます）",
                "migration.order_unknown": "の order に、この計画が変えも消しもしないノードがあります",
                "migration.edge_end": "の辺の端が、新の構成のノードにありません（この辺は足しません）",
                "migration.no_plan": "という計画がありません"}

#: how many folders infra.exclude may name
EXCLUDE_MAX = 50

#: one per way an infra.exclude entry is wrong (a config.exclude problem's "why"; test_infra_room: a why with no words is red)
EXCLUDE_JA = {"not_a_list": "infra.exclude はフォルダ（プロジェクトの中の相対パス）の一覧で書いてください",
              "not_inside": "はプロジェクトの中の相対パスで書いてください（\"..\"・絶対パス・URL は書けません）",
              "no_folder": "のフォルダがプロジェクトにありません（何も外しません）",
              "outside_link": "はプロジェクトの外のフォルダへの link です（もともと歩かないので、外す物がありません）",
              "too_many": f"infra.exclude のフォルダが {EXCLUDE_MAX} 個を超えています（超えた分は外しません）"}


class Words:
    """The lines the page shows for what a room's read found (boundary §5.2): a problem's, a refusal's. These defaults
    are jsonui-doc's (Japanese, as the page said them first); a page in another language passes its own to read()
    (jui viz: its table's words, ticket 2026-10-22-viz-en-document-tools-words-stay-japanese) — the shapes stay the same.
    Each line names the file (a path inside the room), the line when known, and the kind — never the value found (a
    secret's shape is named by its kind only)."""

    def json_line(self, where: str, line) -> str:
        return f"{where}: {line} 行目の JSON が壊れています"

    def json(self, where: str) -> str:
        return f"{where}: JSON として読めません"

    def secret(self, where: str, path: str, kind: str) -> str:
        return f"{where}: {path} に秘密の形（{SECRET_JA.get(kind, kind)}）があります。値は書けません"

    def schema(self, where: str, path: str, detail: dict | None = None) -> str:
        """What is wrong, by the keyword (the problem's detail); a detail with no words of its own: the schema alone."""
        kw = (detail or {}).get("keyword")
        if kw not in SCHEMA_JA:
            return f"{where}: {path} がスキーマに合いません"
        v = dict(detail)
        if kw == "type":
            v.update(want="か".join(TYPE_JA.get(t, t) for t in v["want"]), found=TYPE_JA.get(v["found"], v["found"]))
        return f"{where}: {path} " + SCHEMA_JA[kw].format(**v)

    def side(self, where: str, path: str, detail: dict) -> str:
        """A load definition's or a price file's problem (SIDE_JA, by its detail's keyword)."""
        return f"{where}: {path} " + SIDE_JA[detail["keyword"]].format(**detail)

    def cost(self, detail: dict) -> str:
        """A line the cost simulator says on its own (COST_JA, by its detail's keyword); an empty service or region
        named as COST_EMPTY_JA says."""
        v = {k: (COST_EMPTY_JA[k] if x == "" and k in COST_EMPTY_JA else x) for k, x in detail.items()}
        return COST_JA[detail["keyword"]].format(**v)

    def reference(self, where: str, path: str, code: str) -> str:
        return f"{where}: {path} の参照が合いません（{code}）"

    def spec_duplicate(self, where: str, path: str) -> str:
        return f"{where}: {path} の spec の key が 2 度あります（先の物を出します）"

    def flow(self, where: str, path: str, code: str) -> str:
        return f"{where}: {path} の flow {FLOW_JA[code]}（{code}）"

    def exclude(self, where: str, path: str, why: str) -> str:
        return f"{where}: {EXCLUDE_JA[why]}" if why in ("not_a_list", "too_many") else f"{where}: {path} {EXCLUDE_JA[why]}"

    def environment_outside(self, where: str, path: str) -> str:
        return f"{where}: {path} が、入れ物（親の group・辺の両端）に無い環境を名指ししています"

    def environment_none(self, where: str, path: str) -> str:
        return f"{where}: {path} は、入れ物（親の group・辺の両端）のどの環境にも無いため外します"

    def spec_ha(self, where: str, path: str) -> str:
        return f"{where}: {path} の spec は Multi-AZ と言いますが ha は言いません（費用と 3D は ha を読みます: ha: multi-az と書いてください）"

    def migration(self, where: str, path: str, code: str) -> str:
        return f"{where}: {path} {MIGRATION_JA[code]}（{code}）"

    def model_too_big(self, folder: str, what: str) -> str:
        return f"{folder}: 部屋のモデルが上限を超えています（{what}）"

    def file_too_large(self, where: str, mb: int) -> str:
        return f"{where}: 1 ファイルの上限（{mb} MB）を超えています"

    def unreadable(self, where: str) -> str:
        return f"{where}: 読めません"

    def not_regular(self, where: str, what: str) -> str:
        return f"{where}: 普通のファイルでないため読みません（{what}）"

    def icon(self, path: str) -> str:
        return f"{CONFIG_NAME}: {path} のアイコンが使えません"

    def other(self, where: str, code: str, message: str) -> str:
        """A code with no words of its own yet: its message, as document_tools wrote it (never the code alone)."""
        return f"{where}: {message}（{code}）"

    def refused(self, reason: str, folder: str) -> str:
        return {"not_a_room": "この部屋は読めません",
                "no_infra": f"{folder} に infra のファイル（*.json）がありません",
                "bad_config": f"{CONFIG_NAME}: infra の設定が正しくありません（dir は部屋の中の相対パス）",
                "too_many_files": f"{folder}: ファイルが多すぎます（{LIMITS['files']} 個まで）",
                "too_large": f"{folder}: ファイルの合計が上限（{LIMITS['total_bytes'] // 1_000_000} MB）を超えています",
                "unreadable": f"{folder}: 読めません"}.get(reason, reason)

    def said(self, kind: str, **v) -> str:
        """A refusal whose usual line would say the wrong thing (Refused's say=)."""
        return {"config_too_big": lambda: f"{CONFIG_NAME} が大きすぎます（{v.get('mb')} MB まで）",
                "config_json_line": lambda: f"{CONFIG_NAME}: {v.get('line')} 行目の JSON が壊れています",
                "config_json": lambda: f"{CONFIG_NAME} が JSON として読めません",
                "infra_object": lambda: f'{CONFIG_NAME}: "infra" はオブジェクト（{{"dir": ..., "icons": {{...}}}}）で書いてください',
                "side_path": lambda: f"{CONFIG_NAME}: infra.{v.get('key')} は部屋の中の相対パスで書いてください",
                "symlink": lambda: f"{v.get('folder')} は symlink を通るため読みません（部屋の中の本物のフォルダに置いてください）",
                "no_infra_skipped": lambda: f"{v.get('folder')} に読める infra のファイル（*.json）がありません（普通のファイルでない物は読みません）",
                }[kind]()


DEFAULT_WORDS = Words()


def short(p: dict, folder: str, words: Words = DEFAULT_WORDS) -> str:
    """One line the page can show as it is, in ``words``' language."""
    f = p.get("file") or ""
    where = f if f == CONFIG_NAME or not f else f"{folder}/{f}"
    code = p["code"]
    if (p.get("detail") or {}).get("keyword") in SIDE_JA:
        return words.side(where, p["path"], p["detail"])
    if code == "json":
        return words.json_line(where, p["line"]) if p.get("line") else words.json(where)
    if code.startswith("secret."):
        return words.secret(where, p["path"], code[7:])
    if code == "schema":
        return words.schema(where, p["path"], p.get("detail"))
    if code in ("environment.conflict", "environment.missing", "id.duplicate", "group.missing", "group.cycle", "edge.missing"):
        return words.reference(where, p["path"], code)
    if code == "spec.duplicate":
        return words.spec_duplicate(where, p["path"])
    if code in FLOW_JA:
        return words.flow(where, p["path"], code)
    if code in MIGRATION_JA:
        return words.migration(where, p["path"], code)
    if code == "config.migrations_dir":
        return words.said("side_path", key="migrations_dir")
    if code == "model.too_big":
        return words.model_too_big(folder, p["path"].lstrip("/"))
    if code == "read.too_large":
        return words.file_too_large(where, LIMITS["file_bytes"] // 1_000_000)
    if code == "read.unreadable":
        return words.unreadable(where)
    if code == "read.not_regular":
        return words.not_regular(where, p["message"].split(",")[0])
    if code in ("config.icon", "read.icon"):
        return words.icon(p["path"])
    if code == "config.exclude" and p.get("why") in EXCLUDE_JA:
        return words.exclude(where, p["path"], p["why"])
    if code == "environment.outside":
        return words.environment_outside(where, p["path"])
    if code == "environment.none":
        return words.environment_none(where, p["path"])
    if code == "spec.ha":
        return words.spec_ha(where, p["path"])
    return words.other(where, code, p.get("message") or "")


def cost_short(w: dict, words: Words = DEFAULT_WORDS) -> str:
    """A cost warning's line in ``words``' language: its words (COST_JA) when it has them, else its message."""
    kw = (w.get("detail") or {}).get("keyword")
    return words.cost(w["detail"]) if kw in COST_JA else w.get("message", "")


def _short_refused(reason: str, folder: str, words: Words = DEFAULT_WORDS) -> str:
    return words.refused(reason, folder)


class Refused(Exception):
    """The room cannot be read at all: ``reason`` is one of REASONS; ``short`` the line for the page, when the reason's
    usual one would say the wrong thing."""

    def __init__(self, reason: str, message: str, short: str | None = None, say: tuple | None = None) -> None:
        super().__init__(message)
        self.reason, self.message, self.short, self.say = reason, message, short, say   # say: (kind, values) for Words.said

    def line(self, folder: str, words: "Words") -> str:
        if self.short:
            return self.short
        return words.said(self.say[0], **self.say[1]) if self.say else words.refused(self.reason, folder)


# ---------------------------------------------------------------- opening inside the room

def open_inside(root: Path, rel: str) -> int | None:
    """An fd of root/rel opened one part at a time from root's real path, every part O_NOFOLLOW (a symlink anywhere
    below the root, '.', '..' or an empty part: None), the last part O_NONBLOCK too (a FIFO never holds the open)."""
    flags_dir = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parts = PurePosixPath(rel).parts
    if not parts or any(p in ("", ".", "..", "/") for p in parts):
        return None
    try:
        fd = os.open(str(Path(root).resolve()), flags_dir)
    except OSError:
        return None
    try:
        for k, part in enumerate(parts):
            last = k == len(parts) - 1
            nxt = os.open(part, (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK) if last else flags_dir, dir_fd=fd)
            os.close(fd)
            fd = nxt
        out, fd = fd, None
        return out
    except OSError:
        return None
    finally:
        if fd is not None:
            os.close(fd)


TOO_BIG = object()


def read_capped(root: Path, rel: str, cap: int):
    """The bytes of a regular file under the room (at most cap; a bigger one, or one grown past it while read: TOO_BIG),
    or None (not there, not a regular file, a symlink on the way, unreadable)."""
    fd = open_inside(root, rel)
    if fd is None:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        if st.st_size > cap:
            return TOO_BIG
        chunks, n = [], 0
        while n <= cap:
            b = os.read(fd, min(1 << 16, cap + 1 - n))
            if not b:
                break
            chunks.append(b)
            n += len(b)
        return TOO_BIG if n > cap else b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def _list_dir(root: Path, rel: str, skipped: list | None = None) -> list[tuple[str, int]] | None:
    """(name, size) of the regular *.json files directly in root/rel (no symlink on the way, none followed), by name;
    None when the folder is not there. Hidden names and *.check-report.json are not the model; a *.json that is not a
    regular file (a symlink, a FIFO, a folder) is not read, and goes into ``skipped`` as (name, what it is)."""
    fd = open_inside(root, rel)
    if fd is None:
        return None
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            return None
        out = []
        for name in sorted(os.listdir(fd)):
            if not name.endswith(".json") or name.startswith(".") or name.endswith(".check-report.json"):
                continue
            try:
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                out.append((name, st.st_size))
            elif skipped is not None:
                what = ("a symlink" if stat.S_ISLNK(st.st_mode) else "a FIFO" if stat.S_ISFIFO(st.st_mode)
                        else "a folder" if stat.S_ISDIR(st.st_mode) else "not a regular file")
                skipped.append((name, what))
        return out
    except OSError:
        return None
    finally:
        os.close(fd)


def _symlink_on_the_way(root: Path, rel: str) -> bool:
    """Whether a part of root/rel (below the root) is a symlink: the folder is there, but not reached as the rules
    allow — a different reason from "there is no folder"."""
    cur = Path(root).resolve()
    for part in PurePosixPath(rel).parts:
        cur = cur / part
        try:
            if stat.S_ISLNK(os.lstat(cur).st_mode):
                return True
        except OSError:
            return False
    return False


# ---------------------------------------------------------------- jui.config.json's "infra"

def _rel_ok(raw) -> bool:
    if not isinstance(raw, str) or not raw or len(raw) > 300 or "\\" in raw or "://" in raw:
        return False
    p = PurePosixPath(raw)
    return not p.is_absolute() and all(part not in ("", ".", "..") for part in p.parts)


def _infra_section(root: Path) -> dict | None:
    """The room's jui.config.json "infra" object, or None (no config, no "infra"). Raises Refused("bad_config") when
    the config cannot be read or "infra" is not an object."""
    raw = read_capped(root, CONFIG_NAME, LIMITS["config_bytes"])
    if raw is None:
        return None
    if raw is TOO_BIG:
        raise Refused("bad_config", f"{CONFIG_NAME} is larger than {LIMITS['config_bytes']} bytes",
                      say=("config_too_big", {"mb": LIMITS["config_bytes"] // 1_000_000}))
    try:
        cfg = json.loads(raw.decode("utf-8-sig"))        # a BOM some editors write is not an error
    except json.JSONDecodeError as exc:
        raise Refused("bad_config", f"{CONFIG_NAME} is not JSON (line {exc.lineno})",
                      say=("config_json_line", {"line": exc.lineno})) from None
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise Refused("bad_config", f"{CONFIG_NAME} is not JSON", say=("config_json", {})) from None
    infra = cfg.get("infra") if isinstance(cfg, dict) else None
    if infra is not None and not isinstance(infra, dict):
        raise Refused("bad_config", f'{CONFIG_NAME}: "infra" must be an object',
                      say=("infra_object", {}))
    return infra


def infra_config(root: Path) -> tuple[str, dict[str, str], list[dict]]:
    """(the folder, the icons usable, problems) from the room's jui.config.json. Raises Refused("bad_config") when the
    folder it names is not a relative path inside the room; an icon that breaks the rules is left out with a problem
    (code config.icon). No config, or no "infra": the defaults."""
    infra = _infra_section(root)
    if infra is None:
        return DEFAULT_DIR, {}, []
    folder = infra.get("dir", DEFAULT_DIR)
    if not _rel_ok(folder):
        raise Refused("bad_config", f'{CONFIG_NAME}: infra.dir must be a relative path inside the room (no "..", '
                                    "no absolute path, no URL)")
    problems, icons = [], {}
    raw_icons = infra.get("icons", {})
    if not isinstance(raw_icons, dict):
        problems.append(M._problem(CONFIG_NAME, "/infra/icons", "config.icon", "infra.icons must be an object"))
        raw_icons = {}
    for key, path in list(raw_icons.items()):
        # a key that is not one of the three forms may be anything (a value): never shown
        where = f"/infra/icons/{key}" if ICON_KEY.match(key) and not M.secret_findings(key) else "/infra/icons/<key>"
        if len(icons) >= LIMITS["icons"]:
            problems.append(M._problem(CONFIG_NAME, where, "config.icon", f"more than {LIMITS['icons']} icons"))
            break
        if not ICON_KEY.match(key):
            problems.append(M._problem(CONFIG_NAME, where, "config.icon",
                                       "the key must be service:<provider>/<service>, provider:<provider> or category:<category>"))
        elif M.secret_findings(key):            # one of the forms, holding a secret's shape: never taken, never shown
            problems.append(M._problem(CONFIG_NAME, where, "config.icon", "the key holds the shape of a secret"))
        elif isinstance(path, str) and "://" in path:
            problems.append(M._problem(CONFIG_NAME, where, "config.icon",
                                       "a URL is not read (only an image inside the room: jui viz loads nothing from outside)"))
        elif not _rel_ok(path) or PurePosixPath(path).suffix.lower() not in ICON_TYPES:
            problems.append(M._problem(CONFIG_NAME, where, "config.icon",
                                       "must be a relative path inside the room to a .svg, .png or .webp"))
        elif key.startswith("category:") and key[9:] not in M.vocabulary("category"):
            problems.append(M._problem(CONFIG_NAME, where, "config.icon", "names a category the model does not have"))
        else:
            icons[key] = path
    return folder, icons, problems + exclude_problems(root, infra)


def _exclude_problem(where: str, why: str, message: str, severity: str = "error") -> dict:
    """A config.exclude problem; ``why`` (one of EXCLUDE_JA) says which way the entry is wrong, for its line."""
    return dict(M._problem(CONFIG_NAME, where, "config.exclude", message, severity), why=why)


def _exclude_entries(root: Path, infra: dict | None) -> tuple[list[str], list[dict]]:
    """(the folders infra.exclude names that are there, the problems with the rest)."""
    raw = (infra or {}).get("exclude")
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [_exclude_problem("/infra/exclude", "not_a_list",
                                     "infra.exclude must be a list of folders (relative paths inside the project)")]
    out, problems = [], []
    real_root = root.resolve()
    for i, item in enumerate(raw[:EXCLUDE_MAX]):
        where = f"/infra/exclude/{i}"
        rel = item.rstrip("/") if isinstance(item, str) else item
        if not _rel_ok(rel):
            problems.append(_exclude_problem(where, "not_inside",
                                             'must be a relative path inside the project (no "..", no absolute path, no URL)'))
            continue
        target = root / rel
        if not target.is_dir():
            problems.append(_exclude_problem(where, "no_folder",
                                             f"{rel}: no such folder in the project: nothing is left out for it", "warning"))
            continue
        try:
            target.resolve().relative_to(real_root)
        except ValueError:
            problems.append(_exclude_problem(where, "outside_link",
                                             f"{rel}: a link to a folder outside the project: never walked, nothing to leave out"))
            continue
        out.append(rel)
    if len(raw) > EXCLUDE_MAX:
        problems.append(_exclude_problem("/infra/exclude", "too_many",
                                         f"more than {EXCLUDE_MAX} folders: the rest are not left out"))
    return out, problems


def exclude_problems(root: Path, infra: dict | None) -> list[dict]:
    return _exclude_entries(root, infra)[1]


def infra_exclude(root: Path) -> list[str]:
    """The folders jui.config.json's infra.exclude names (another project's: a submodule, a product of its own), as
    relative paths that are there: seed and the infra checks do not walk into them (iac_tables.walk_project). What is
    wrong with the list is said by validate infra (infra_config's problems), never silently dropped. A config that
    cannot be read: none (infra_config refuses it where it is read)."""
    try:
        infra = _infra_section(root)
    except Refused:
        return []
    return _exclude_entries(root, infra)[0]


def side_dir(root: Path, key: str) -> str:
    """The folder of the cost simulator's files (plan docs/plans/2026-10-20-jui-viz-backend-load-and-cost-simulator.md):
    key "load_dir" (the load definitions) or "prices_dir" (the price files), from jui.config.json's infra; default
    <infra.dir>/load and <infra.dir>/prices. Raises Refused("bad_config") as infra.dir does."""
    infra = _infra_section(root) or {}
    folder = infra.get("dir", DEFAULT_DIR)
    if not _rel_ok(folder):
        raise Refused("bad_config", f'{CONFIG_NAME}: infra.dir must be a relative path inside the room (no "..", '
                                    "no absolute path, no URL)")
    side = infra.get(key, f"{folder}/{key.split('_')[0]}")
    if not _rel_ok(side):
        raise Refused("bad_config", f'{CONFIG_NAME}: infra.{key} must be a relative path inside the room (no "..", '
                                    "no absolute path, no URL)",
                      say=("side_path", {"key": key}))
    return side


def read_json_folder(root: Path, folder: str) -> tuple[list[tuple[str, bytes]], list[dict]]:
    """The regular *.json files directly in root/folder as (name, bytes), read as the model's are (one part at a time
    with O_NOFOLLOW, LIMITS), and problems (read.*). An empty list: none, or the folder is not there. Raises Refused
    (too_many_files, too_large, unreadable for a symlink on the way)."""
    root = Path(root)
    skipped: list = []
    listed = _list_dir(root, folder, skipped)
    if listed is None and _symlink_on_the_way(root, folder):
        raise Refused("unreadable", f"{folder} is reached through a symlink: not read",
                      say=("symlink", {"folder": folder}))
    problems = [M._problem(name, "/", "read.not_regular", f"{what}, not a regular file: not read", "warning")
                for name, what in skipped]
    listed = listed or []
    if len(listed) > LIMITS["files"]:
        raise Refused("too_many_files", f"{len(listed)} files in {folder}; at most {LIMITS['files']} are read")
    if sum(size for _n, size in listed) > LIMITS["total_bytes"]:
        raise Refused("too_large", f"the files in {folder} are over {LIMITS['total_bytes']} bytes together")
    files, total = [], 0
    for name, _size in listed:
        raw = read_capped(root, f"{folder}/{name}", min(LIMITS["file_bytes"], LIMITS["total_bytes"] - total))
        if raw is TOO_BIG:
            problems.append(M._problem(name, "/", "read.too_large", f"over {LIMITS['file_bytes']} bytes: not read"))
        elif raw is None:
            problems.append(M._problem(name, "/", "read.unreadable", "could not be read as a regular file"))
        else:
            total += len(raw)
            files.append((name, raw))
    return files, problems


def read_icon(root: Path, path: str) -> tuple[bytes, str] | None:
    """(bytes, media type) of one configured icon inside the room, within LIMITS["icon_bytes"]; None otherwise."""
    if not _rel_ok(path):
        return None
    media = ICON_TYPES.get(PurePosixPath(path).suffix.lower())
    raw = read_capped(root, path, LIMITS["icon_bytes"]) if media else None
    return (raw, media) if isinstance(raw, bytes) else None


# ---------------------------------------------------------------- counting and reading a room

def counts(root: Path) -> dict:
    """{"files": n, "dir": folder} — the model's files by their names and sizes only (nothing is opened but the
    folder and jui.config.json). n is 0 when there is none, or when the room's config cannot be used."""
    try:
        folder, _icons, _p = infra_config(Path(root))
    except Refused:
        return {"files": 0, "dir": DEFAULT_DIR}
    listed = _list_dir(Path(root), folder) or []
    return {"files": len(listed), "dir": folder}


def read(root: Path, is_room: bool = True, words: Words = DEFAULT_WORDS, plans: bool | str = False) -> dict:
    """The room's model as the page takes it (§5.2): {ok, version, dir, files, environments, groups, nodes, edges,
    problems, icons, readMs}, or {ok: False, reason, message} when nothing could be read. ``plans``: True, the room's
    migration plans too (migration.report: "migrations", only when the room has one); a name, that plan alone.
    Blocking: call it off the event loop."""
    t0 = time.monotonic()
    root = Path(root)
    try:
        if not is_room:
            raise Refused("not_a_room", "not a room jui viz knows")
        folder, icons, problems = infra_config(root)
        skipped: list = []
        listed = _list_dir(root, folder, skipped)
        if listed is None and _symlink_on_the_way(root, folder):
            raise Refused("unreadable", f"{folder} is reached through a symlink: not read",
                          say=("symlink", {"folder": folder}))
        for name, what in skipped:
            problems.append(M._problem(name, "/", "read.not_regular", f"{what}, not a regular file: not read", "warning"))
        if not listed:
            refused = Refused("no_infra", f"no model files in {folder} (*.json)",
                              say=("no_infra_skipped", {"folder": folder}) if skipped else None)
            refused.problems = problems                 # the warnings say why: they go with the refusal
            raise refused
        if len(listed) > LIMITS["files"]:
            raise Refused("too_many_files", f"{len(listed)} files in {folder}; at most {LIMITS['files']} are read")
        if sum(size for _n, size in listed) > LIMITS["total_bytes"]:
            raise Refused("too_large", f"the files in {folder} are over {LIMITS['total_bytes']} bytes together")
        files, total = [], 0
        for name, _size in listed:
            raw = read_capped(root, f"{folder}/{name}", min(LIMITS["file_bytes"], LIMITS["total_bytes"] - total))
            if raw is TOO_BIG:
                problems.append(M._problem(name, "/", "read.too_large", f"over {LIMITS['file_bytes']} bytes: not read"))
                continue
            if raw is None:
                problems.append(M._problem(name, "/", "read.unreadable", "could not be read as a regular file"))
                continue
            total += len(raw)
            files.append((name, raw))
        model, found = M.merge(files)
        problems.extend(found)
        if not model["files"]:                 # every file was left out: nothing to show, the first error says why
            first = next((p for p in problems if p["severity"] == "error"), None)
            for p in problems:
                p["short"] = short(p, folder, words)
            return {"ok": False, "reason": "invalid", "dir": folder,
                    "message": "no model file could be used", "short": first["short"] if first else folder,
                    "problems": problems}
        for key, path in list(icons.items()):
            if read_icon(root, path) is None:      # only keys of the three forms with no secret's shape got here
                problems.append(M._problem(CONFIG_NAME, f"/infra/icons/{key}", "read.icon",
                                           "the image is not there, not a regular file, or too big"))
                del icons[key]
    except Refused as r:
        folder = locals().get("folder") or DEFAULT_DIR
        out = {"ok": False, "reason": r.reason, "message": r.message, "short": r.line(folder, words)}
        if getattr(r, "problems", None):
            for p in r.problems:
                p["short"] = short(p, folder, words)
            out["problems"] = r.problems
        return out
    except OSError as exc:
        folder = locals().get("folder") or DEFAULT_DIR
        return {"ok": False, "reason": "unreadable", "message": f"reading failed ({exc.strerror or type(exc).__name__})",
                "short": words.refused("unreadable", folder)}
    for p in problems:
        p["short"] = short(p, folder, words)
    out = {"ok": True, "dir": folder}
    out.update(model)
    out.update(problems=problems, icons=icons)
    if plans:
        from . import migration as MG
        try:
            got = MG.report(root, files, problems, None if plans is True else plans, folder, words)
        except Refused as r:          # infra.migrations_dir is not a path inside the room
            got = [{"name": "", "dir": "", "ok": False, "steps": [], "counts": {},
                    "problems": [dict(M._problem(CONFIG_NAME, "/infra/migrations_dir", "config.migrations_dir", r.message),
                                      short=r.line(folder, words))]}]
        if got is not None:
            out["migrations"] = got
    out["readMs"] = int((time.monotonic() - t0) * 1000)
    return out
