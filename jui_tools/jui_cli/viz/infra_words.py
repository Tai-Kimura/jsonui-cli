"""The server room's words that come from document_tools, in the page's language (ticket
2026-10-22-viz-en-document-tools-words-stay-japanese).

document_tools says them in Japanese by default: a room's problem and refusal lines (infra/room.py Words), a cost
meter's name and the month's "others" (infra/cost/view.py Labels, from the load schema's x-label). jui viz passes
these in their place, each word from its own table (web/i18n, keys srv.room.* and srv.cost.*): the shapes
document_tools gives (and jsonui-doc prints) stay as they are, and the Japanese table's words are document_tools'
own, letter for letter (tests/test_viz_infra_words.py).
"""
from __future__ import annotations

from . import i18n

CONFIG_NAME = "jui.config.json"

# Each word's key, named as it is (the table's gate finds a key used by its name in the code).

#: a quantity's name (the load schema's x-label)
QUANTITY = {
    "requests": "srv.cost.q.requests", "ecpu": "srv.cost.q.ecpu", "state_transitions": "srv.cost.q.state_transitions",
    "read_units": "srv.cost.q.read_units", "write_units": "srv.cost.q.write_units",
    "get_requests": "srv.cost.q.get_requests", "put_requests": "srv.cost.q.put_requests",
    "rows_read": "srv.cost.q.rows_read", "rows_written": "srv.cost.q.rows_written", "messages": "srv.cost.q.messages",
    "egress_gb": "srv.cost.q.egress_gb", "transfer_gb": "srv.cost.q.transfer_gb",
    "cdn_egress_gb": "srv.cost.q.cdn_egress_gb", "processed_gb": "srv.cost.q.processed_gb",
    "log_ingest_gb": "srv.cost.q.log_ingest_gb", "new_connections": "srv.cost.q.new_connections",
    "rule_evaluations": "srv.cost.q.rule_evaluations", "emails": "srv.cost.q.emails",
    "input_tokens": "srv.cost.q.input_tokens", "output_tokens": "srv.cost.q.output_tokens",
    "build_minutes": "srv.cost.q.build_minutes", "lcu": "srv.cost.q.lcu",
    "active_connections": "srv.cost.q.active_connections", "concurrency": "srv.cost.q.concurrency",
    "capacity_units": "srv.cost.q.capacity_units", "read_capacity_units": "srv.cost.q.read_capacity_units",
    "write_capacity_units": "srv.cost.q.write_capacity_units", "vcpu": "srv.cost.q.vcpu",
    "memory_gb": "srv.cost.q.memory_gb", "storage_gb": "srv.cost.q.storage_gb",
    "monthly_active_users": "srv.cost.q.monthly_active_users", "secrets": "srv.cost.q.secrets",
    "metrics": "srv.cost.q.metrics", "rules": "srv.cost.q.rules", "duration_ms": "srv.cost.q.duration_ms",
    "cpu_ms": "srv.cost.q.cpu_ms", "memory_mb": "srv.cost.q.memory_mb"
}

#: a meter no quantity names (view.METER_LABELS)
METER = {
    "instance": "srv.cost.meter.instance", "hour": "srv.cost.meter.hour", "cluster": "srv.cost.meter.cluster",
    "storage": "srv.cost.meter.storage", "vcpu": "srv.cost.meter.vcpu", "memory": "srv.cost.meter.memory",
    "lcu": "srv.cost.meter.lcu", "capacity": "srv.cost.meter.capacity", "shard": "srv.cost.meter.shard",
    "plan": "srv.cost.meter.plan", "egress": "srv.cost.meter.egress",
    "transfer-regional": "srv.cost.meter.transfer_regional",
    "transfer-inter-region": "srv.cost.meter.transfer_inter_region"
}

#: a secret's kind (room.SECRET_JA)
SECRET = {
    "arn": "srv.room.secret.arn", "account_id": "srv.room.secret.account_id",
    "ip_address": "srv.room.secret.ip_address", "connection_string": "srv.room.secret.connection_string",
    "url_credentials": "srv.room.secret.url_credentials", "private_key": "srv.room.secret.private_key",
    "access_key": "srv.room.secret.access_key", "token": "srv.room.secret.token",
    "password": "srv.room.secret.password"
}

#: a flow problem (room.FLOW_JA)
FLOW = {
    "flow.node.missing": "srv.room.flow.node.missing", "flow.edge.missing": "srv.room.flow.edge.missing",
    "flow.discontinuous": "srv.room.flow.discontinuous", "flow.step.kind": "srv.room.flow.step.kind",
    "flow.paths_disagree": "srv.room.flow.paths_disagree", "flow.too_deep": "srv.room.flow.too_deep",
    "flow.choice.duplicate": "srv.room.flow.choice.duplicate", "flow.choice.kind": "srv.room.flow.choice.kind",
    "flow.default.missing": "srv.room.flow.default.missing", "flow.join.missing": "srv.room.flow.join.missing",
    "flow.join.backward": "srv.room.flow.join.backward", "flow.goto.missing": "srv.room.flow.goto.missing",
    "flow.goto.jump": "srv.room.flow.goto.jump", "flow.default_cycle": "srv.room.flow.default_cycle",
    "flow.env.partial": "srv.room.flow.env.partial", "flow.id.duplicate": "srv.room.flow.id.duplicate",
    "flow.schedule.trigger": "srv.room.flow.schedule.trigger"
}

#: a keyword a schema problem breaks (room.SCHEMA_JA)
SCHEMA = {
    "maxLength": "srv.room.schema.maxLength", "minLength": "srv.room.schema.minLength",
    "pattern": "srv.room.schema.pattern", "enum": "srv.room.schema.enum", "const": "srv.room.schema.const",
    "type": "srv.room.schema.type", "oneOf": "srv.room.schema.oneOf", "required": "srv.room.schema.required",
    "additionalProperties": "srv.room.schema.additionalProperties", "minimum": "srv.room.schema.minimum",
    "maximum": "srv.room.schema.maximum", "exclusiveMinimum": "srv.room.schema.exclusiveMinimum",
    "finite": "srv.room.schema.finite", "minItems": "srv.room.schema.minItems",
    "maxItems": "srv.room.schema.maxItems", "uniqueItems": "srv.room.schema.uniqueItems",
    "propertyNames": "srv.room.schema.propertyNames", "minProperties": "srv.room.schema.minProperties",
    "maxProperties": "srv.room.schema.maxProperties"
}

#: a load definition's or a price file's problem, by its words key (room.SIDE_JA)
SIDE = {
    "load.timezone": "srv.room.side.load.timezone", "load.date.calendar": "srv.room.side.load.date.calendar",
    "load.date.month": "srv.room.side.load.date.month", "load.date.twice": "srv.room.side.load.date.twice",
    "load.ref": "srv.room.side.load.ref", "load.rule": "srv.room.side.load.rule",
    "load.minmax": "srv.room.side.load.minmax", "load.minmax.rule": "srv.room.side.load.minmax.rule",
    "load.minmax.step": "srv.room.side.load.minmax.step",
    "load.autoscale.per_instance": "srv.room.side.load.autoscale.per_instance",
    "load.autoscale.vertical": "srv.room.side.load.autoscale.vertical",
    "load.flow_unwritten": "srv.room.side.load.flow_unwritten",
    "load.ladder.duplicate": "srv.room.side.load.ladder.duplicate",
    "load.ladder.amount": "srv.room.side.load.ladder.amount", "load.ladder.grow": "srv.room.side.load.ladder.grow",
    "load.ladder.not_step": "srv.room.side.load.ladder.not_step",
    "load.ladder.quantity": "srv.room.side.load.ladder.quantity",
    "load.ladder.rule": "srv.room.side.load.ladder.rule", "load.target.node": "srv.room.side.load.target.node",
    "load.target.edge": "srv.room.side.load.target.edge",
    "load.environment.none": "srv.room.side.load.environment.none",
    "load.environment.unknown": "srv.room.side.load.environment.unknown",
    "load.node_missing": "srv.room.side.load.node_missing",
    "load.not_in_environment": "srv.room.side.load.not_in_environment",
    "load.select_none": "srv.room.side.load.select_none", "load.overlap.own": "srv.room.side.load.overlap.own",
    "load.overlap.later": "srv.room.side.load.overlap.later", "load.sku.multi_az": "srv.room.side.load.sku.multi_az",
    "load.quantity_unused": "srv.room.side.load.quantity_unused",
    "load.schedule_unused": "srv.room.side.load.schedule_unused",
    "load.edge_missing": "srv.room.side.load.edge_missing",
    "load.edge_ambiguous": "srv.room.side.load.edge_ambiguous",
    "load.while_stopped": "srv.room.side.load.while_stopped", "load.id.duplicate": "srv.room.side.load.id.duplicate",
    "prices.row.exactly_one": "srv.room.side.prices.row.exactly_one",
    "prices.row.effective": "srv.room.side.prices.row.effective",
    "prices.row.tier_start": "srv.room.side.prices.row.tier_start",
    "prices.row.tier_end": "srv.room.side.prices.row.tier_end",
    "prices.row.tier_open": "srv.room.side.prices.row.tier_open",
    "prices.row.tier_gap": "srv.room.side.prices.row.tier_gap", "prices.duplicate": "srv.room.side.prices.duplicate"
}

#: a line the cost simulator says on its own, by its words key (room.COST_JA)
COST = {
    "cost.rule_failed": "srv.room.cost.cost.rule_failed", "cost.no_price": "srv.room.cost.cost.no_price",
    "cost.no_price.transfer": "srv.room.cost.cost.no_price.transfer",
    "cost.free_per_scenario": "srv.room.cost.cost.free_per_scenario",
    "cost.account_other_month": "srv.room.cost.cost.account_other_month",
    "cost.stepfunctions_no_transitions": "srv.room.cost.cost.stepfunctions_no_transitions",
    "cost.apprunner_active_upper_bound": "srv.room.cost.cost.apprunner_active_upper_bound",
    "cost.waf_kind.said": "srv.room.cost.cost.waf_kind.said",
    "cost.waf_kind.default": "srv.room.cost.cost.waf_kind.default",
    "cost.free_not_counted.run": "srv.room.cost.cost.free_not_counted.run",
    "cost.free_not_counted.gke": "srv.room.cost.cost.free_not_counted.gke",
    "prices.cache_unused": "srv.room.cost.prices.cache_unused",
    "prices.cache_other_version": "srv.room.cost.prices.cache_other_version",
    "prices.free_dropped": "srv.room.cost.prices.free_dropped",
    "prices.free_dropped.pool": "srv.room.cost.prices.free_dropped.pool",
    "prices.room_unused": "srv.room.cost.prices.room_unused"
}

#: an empty value in a cost line (room.COST_EMPTY_JA)
COST_EMPTY = {
    "service": "srv.room.cost.empty.service", "region": "srv.room.cost.empty.region"
}

#: a JSON type's name (room.TYPE_JA)
TYPE = {
    "object": "srv.room.type.object", "array": "srv.room.type.array", "string": "srv.room.type.string",
    "integer": "srv.room.type.integer", "number": "srv.room.type.number", "boolean": "srv.room.type.boolean",
    "null": "srv.room.type.null"
}

#: a migration plan's problem (room.MIGRATION_JA)
MIGRATION = {
    "migration.remove_missing": "srv.room.migration.remove_missing", "migration.duplicate": "srv.room.migration.duplicate",
    "migration.both": "srv.room.migration.both", "migration.order_unknown": "srv.room.migration.order_unknown",
    "migration.edge_end": "srv.room.migration.edge_end", "migration.no_plan": "srv.room.migration.no_plan"
}

#: a way an infra.exclude entry is wrong (room.EXCLUDE_JA)
EXCLUDE = {
    "not_a_list": "srv.room.exclude.not_a_list", "not_inside": "srv.room.exclude.not_inside",
    "no_folder": "srv.room.exclude.no_folder", "outside_link": "srv.room.exclude.outside_link",
    "too_many": "srv.room.exclude.too_many"
}

#: a refusal's line
REFUSED = {
    "not_a_room": "srv.room.refused.not_a_room", "no_infra": "srv.room.refused.no_infra",
    "bad_config": "srv.room.refused.bad_config", "too_many_files": "srv.room.refused.too_many_files",
    "too_large": "srv.room.refused.too_large", "unreadable": "srv.room.refused.unreadable"
}

#: a refusal whose usual line would say the wrong thing (room's say=)
SAID = {
    "config_too_big": "srv.room.said.config_too_big", "config_json_line": "srv.room.said.config_json_line",
    "config_json": "srv.room.said.config_json", "infra_object": "srv.room.said.infra_object",
    "side_path": "srv.room.said.side_path", "symlink": "srv.room.said.symlink",
    "no_infra_skipped": "srv.room.said.no_infra_skipped"
}


class RoomWords:
    """infra/room.py Words, from the table."""

    def __init__(self, limits: dict, exclude_max: int) -> None:
        self.limits, self.exclude_max = limits, exclude_max

    def json_line(self, where, line):
        return i18n.tl("srv.room.json.line", where=where, line=line)

    def json(self, where):
        return i18n.tl("srv.room.json", where=where)

    def secret(self, where, path, kind):
        return i18n.tl("srv.room.secret", where=where, path=path, kind=i18n.tl(SECRET[kind]) if kind in SECRET else kind)

    def schema(self, where, path, detail=None):
        kw = (detail or {}).get("keyword")
        if kw not in SCHEMA:
            return i18n.tl("srv.room.schema", where=where, path=path)
        v = {k: x for k, x in detail.items() if k != "keyword"}
        if kw == "type":
            name = lambda t: i18n.tl(TYPE[t]) if t in TYPE else t  # noqa: E731
            v.update(want=i18n.tl("srv.room.type.or").join(name(t) for t in v["want"]), found=name(v["found"]))
        return i18n.tl(SCHEMA[kw], where=where, path=path, **v)

    def side(self, where, path, detail):
        return i18n.tl(SIDE[detail["keyword"]], where=where, path=path, **{k: v for k, v in detail.items() if k != "keyword"})

    def cost(self, detail):
        v = {k: (i18n.tl(COST_EMPTY[k]) if x == "" and k in COST_EMPTY else x) for k, x in detail.items() if k != "keyword"}
        return i18n.tl(COST[detail["keyword"]], **v)

    def reference(self, where, path, code):
        return i18n.tl("srv.room.reference", where=where, path=path, code=code)

    def spec_duplicate(self, where, path):
        return i18n.tl("srv.room.spec.duplicate", where=where, path=path)

    def flow(self, where, path, code):
        return i18n.tl("srv.room.flow", where=where, path=path, why=i18n.tl(FLOW[code]), code=code)

    def exclude(self, where, path, why):
        return i18n.tl(EXCLUDE[why], where=where, path=path, n=self.exclude_max)

    def migration(self, where, path, code):
        return i18n.tl("srv.room.migration", where=where, path=path, why=i18n.tl(MIGRATION[code]), code=code)

    def environment_outside(self, where, path):
        return i18n.tl("srv.room.environment.outside", where=where, path=path)

    def environment_none(self, where, path):
        return i18n.tl("srv.room.environment.none", where=where, path=path)

    def spec_ha(self, where, path):
        return i18n.tl("srv.room.spec.ha", where=where, path=path)

    def model_too_big(self, folder, what):
        return i18n.tl("srv.room.model.too_big", folder=folder, what=what)

    def file_too_large(self, where, mb):
        return i18n.tl("srv.room.file.too_large", where=where, mb=mb)

    def unreadable(self, where):
        return i18n.tl("srv.room.unreadable", where=where)

    def not_regular(self, where, what):
        return i18n.tl("srv.room.not_regular", where=where, what=what)

    def icon(self, path):
        return i18n.tl("srv.room.icon", config=CONFIG_NAME, path=path)

    def other(self, where, code, message):
        return i18n.tl("srv.room.other", where=where, message=message, code=code)

    def refused(self, reason, folder):
        if reason not in REFUSED:
            return reason
        return i18n.tl(REFUSED[reason], folder=folder, config=CONFIG_NAME, n=self.limits["files"],
                       mb=self.limits["total_bytes"] // 1_000_000)

    def said(self, kind, **v):
        if "key" in v:               # infra.<key>: tl's own first argument is key
            v["name"] = v.pop("key")
        return i18n.tl(SAID[kind], config=CONFIG_NAME, shape='{"dir": ..., "icons": {...}}', **v)


class CostLabels:
    """infra/cost/view.py Labels, from the table: a quantity's name (srv.cost.q.<quantity>, the load schema's
    x-label in Japanese), a meter no quantity names (srv.cost.meter.<name>), one model's tokens, the others."""

    def quantity(self, qid, label):
        return i18n.tl(QUANTITY[qid]) if qid in QUANTITY else label

    def meter(self, name):
        return i18n.tl(METER[name]) if name in METER else name

    def model(self, label, model):
        return i18n.tl("srv.cost.model", label=label, model=model)

    def others(self, n):
        return i18n.tl("cost.others", n=n)
