# Writing a server room: `docs/infra`

`jui viz` draws a project's infrastructure as a server room (a 3D room per environment, flows played along its edges,
a cost page), and `jsonui-doc` checks it and prices it. Everything comes from JSON files you write under `docs/infra`.
This guide is the order to write them in, the rules that are easy to get wrong, and what each problem code asks you
to fix. The schemas (`jsonui_doc_cli/infra/infra-*.v0.schema.json`) hold the full field lists.

## The files

| Path | What | Checked by |
|---|---|---|
| `docs/infra/*.json` | The model: environments, groups, nodes, edges, flows (one file or several, merged) | `jsonui-doc validate infra` |
| `docs/infra/load/*.json` | Load scenarios: one environment's month of traffic, for the cost | `jsonui-doc validate infra-load` |
| `docs/infra/prices/*.json` | Prices the bundled table lacks (or that you want to override) | `jsonui-doc validate infra-prices` |
| `docs/infra/seed/` | `jsonui-doc seed infra`'s draft and report — a starting point, never read as the model | — |

`jui.config.json` → `infra` can move them: `dir` (default `docs/infra`), `load_dir`, `prices_dir`, `icons`.
No file may hold a value: an ARN, an account id, an IP, a connection string, a key or a token is refused wherever it
appears. Names and ids only.

## The order

1. **Draft from what the project already says.** `jsonui-doc seed infra` reads Compose, Terraform / OpenTofu,
   Kubernetes, CloudFormation / SAM, `cdk.out`, wrangler, Firebase and PaaS files, and the code's SDK imports and
   environment variable names (never state, `.tfvars` or `.env` values). Read `seed/seed-report.json`: `unmatched`
   and `skipped` are what it could not place. Copy what you keep into `docs/infra/*.json`.
2. **Write the model** — environments, groups (account, region, VPC…), nodes, edges. Then `jsonui-doc validate infra`.
3. **Write the flows** (below), in the model's files. `validate infra` again.
4. **Write a load scenario** per environment and month (below). `jsonui-doc validate infra-load`.
5. **Add prices** only for what `cost infra` says has no price. `jsonui-doc validate infra-prices`.
6. **Price it.** `jsonui-doc cost infra` (`--scenario`, `--by node`, `--date YYYY-MM-DD`, `--json`).
7. **Keep it true.** Declare `builtin:infra-iac`, `builtin:infra-code` and `builtin:infra-load` in `jui.config.json`
   → `checks` and run `jsonui-doc check infra` (`--json` for a machine-readable result).

## A small room

A browser, a load balancer, an API on containers, a Multi-AZ MySQL and a mail service, one flow with a branch, and a
month of load. These three files pass `validate infra`, `validate infra-load`, `validate infra-prices` and
`cost infra` as they are (a test keeps them so).

<!-- file: docs/infra/main.json -->
```json
{
  "version": 0,
  "environments": [{"id": "production", "label": "Production", "kind": "production"}],
  "groups": [{"id": "aws-prod", "kind": "account", "provider": "aws", "label": "Production account", "environments": ["production"]},
             {"id": "tokyo", "kind": "region", "region": "ap-northeast-1", "parent": "aws-prod", "label": "Tokyo"}],
  "nodes": [
    {"id": "browser", "category": "client", "label": "Browser"},
    {"id": "alb", "category": "load_balancer", "service": "elb.alb", "group": "tokyo"},
    {"id": "api", "category": "compute.container", "service": "ecs.fargate", "group": "tokyo", "iac": ["aws_ecs_service.api"]},
    {"id": "db", "category": "database.relational", "service": "rds.mysql", "group": "tokyo", "ha": "multi-az",
     "spec": [{"key": "instance_class", "value": "db.t3.small"}]},
    {"id": "mail", "category": "mail", "provider": "sendgrid", "service": "email", "label": "SendGrid"}
  ],
  "edges": [
    {"from": "browser", "to": "alb", "protocol": "https", "port": 443},
    {"from": "alb", "to": "api", "protocol": "http", "port": 8000},
    {"from": "api", "to": "db", "protocol": "mysql", "port": 3306},
    {"from": "api", "to": "mail", "protocol": "https", "port": 443}
  ],
  "flows": [
    {"id": "order", "label": "Place an order", "start": "browser", "trigger": "user", "steps": [
      {"from": "browser", "to": "alb", "action": "request", "label": "POST /orders"},
      {"from": "alb", "to": "api", "action": "request"},
      {"branch": {"label": "In stock?", "default": "yes", "choices": [
        {"id": "yes", "label": "Yes", "steps": [
          {"from": "api", "to": "db", "action": "write", "label": "Save the order"},
          {"from": "db", "to": "api", "action": "response"},
          {"from": "api", "to": "mail", "action": "request", "async": true, "label": "Send the receipt"},
          {"from": "mail", "to": "api", "action": "response"}]},
        {"id": "no", "label": "No", "join": "reply"}]}},
      {"id": "reply", "from": "api", "to": "alb", "action": "response"},
      {"from": "alb", "to": "browser", "action": "response", "label": "201 or 409"}]}
  ]
}
```

<!-- file: docs/infra/load/ordinary.json -->
```json
{
  "version": 0,
  "id": "ordinary",
  "label": "An ordinary month",
  "environment": "production",
  "month": "2026-11",
  "timezone": "Asia/Tokyo",
  "defaults": {"region": "ap-northeast-1"},
  "profiles": {"day": {"hourly": [0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.5, 0.9, 1.2, 1.2, 1.2, 1.3, 1.4, 1.3, 1.2, 1.2, 1.2, 1.3, 1.6, 1.8, 1.7, 1.3, 0.9, 0.5]}},
  "week": {"mon": "day", "tue": "day", "wed": "day", "thu": "day", "fri": "day", "sat": "day", "sun": "day"},
  "loads": [
    {"node": "alb", "quantities": {"lcu": 1}},
    {"node": "api", "quantities": {"requests": {"amount": 20, "per": "second"}, "vcpu": 0.5, "memory_gb": 1, "egress_gb": {"amount": 30, "per": "day"}}},
    {"node": "db", "sku": "db.t3.small", "quantities": {"storage_gb": 50}},
    {"node": "mail", "quantities": {"emails": {"amount": 500, "per": "day"}}}
  ]
}
```

<!-- file: docs/infra/prices/sendgrid.json -->
```json
{
  "version": 0,
  "id": "sendgrid",
  "prices": [
    {"provider": "sendgrid", "service": "email", "sku": "emails", "region": "global", "unit": "email",
     "price_usd": 0.0006, "effective": "2026-10-01", "source": "https://sendgrid.com/pricing/", "note": "an example price, not a quote"}
  ]
}
```

`jsonui-doc cost infra` on it prints the month's total by provider, the top nodes, and `no rule (1): browser` — a
client is drawn but has no price of its own.

## Flows: the rules that are easy to miss

A flow is where a request (or a device, a schedule, an event) goes, step by step. The flow is always **at one node**;
each move leaves the node it is at and ends at the edge's other end.

| Rule | Wrong | Right |
|---|---|---|
| **A call and its reply are two steps.** `async` too: the flow still moves to the node called. | `api → db [read]`, then `api → alb` | `api → db [read]`, `db → api [response]`, then `api → alb` |
| **A send that does not wait** is the async request and its acknowledgement. | a one-lane `parallel` (refused: at least 2 lanes) | `api → mail [request, async]`, `mail → api [response]` |
| **Lanes leave from where the flow is.** The flow stays there and goes on when all lanes are done. | a lane starting at `browser` while the flow is at `api` | each lane's first step from `api` |
| **A choice goes on after the branch.** No choice ends the flow mid-way. | a choice "→ end" with an error | the choice `join`s the step that sends the reply (give that step an `id`) |
| **One step, one edge.** Each move needs an edge between its two nodes. | `client → alb → api → s3` in one step | three steps; add the missing edge (`flow.edge.missing`) |
| **Leave out name lookups.** A DNS lookup is not a move of the request. | `admin → dns`, then `admin → api` | `admin → api` |
| **The verbs are closed.** `action`: request, response, read, write, upload, download, invoke, enqueue, dequeue, publish, subscribe, auth, schedule. | verify, query, call, notify, run | auth, read, request + response, publish, schedule or invoke |
| **One path per environment set.** A flow listing several environments must have its whole way in each. | production and staging in one flow, staging without the WAF (`flow.env.partial`) | an `order` flow and an `order-stg` flow |
| **Another start is another flow.** | a scheduled job written inside a user's flow | its own flow with `trigger: schedule`; `goto` only to a flow that starts where this one is (`flow.goto.jump` warns otherwise) |

When a move does not leave the node the flow is at, `flow.discontinuous` names the rule its writer most likely missed
(the reply, the lane, the choice).

## Load: the rules that are easy to miss

| Rule | What happens otherwise |
|---|---|
| **One row applies to a node.** A later row for the same node wins and the earlier counts for nothing; a node's own row beats a selector's (`load.overlap`). Put all of the node's quantities in one row. | Traffic written in several rows is not added: only the last row is priced. |
| **A row's `profile` beats the day's shape.** `week`, `days[]` and holidays shape only rows without their own profile. | A campaign day's shape does not reach a row that names a profile. |
| **`days[]` multipliers apply to every row on that date.** | — |
| **Each node reads only some quantities** (`load.quantity_unused` says which are ignored). A load balancer reads `lcu`, not `egress_gb`; Fargate reads `egress_gb`. Put internet egress where its rule reads it, or on an edge. | The quantity is priced as zero. |
| **A SaaS billed by use reads `requests`, and an LLM its tokens** (`input_tokens`, `output_tokens`). Tokens of two models on one node are written by model: `"input_tokens": {"by_sku": {"model-large": 5e7, "model-small": 4.8e7}, "per": "day"}`, priced under `<model>:input-tokens` / `<model>:output-tokens` (unit `token`, `per_units` 1000000); one model can be the row's `sku` instead. With tokens, a price per call is optional. A SaaS with nothing to pay still gets a row (`requests` and a `$0` price) to say it is counted as 0. A CI service reads `build_minutes` (sku `minutes`, unit `minute`). | Without a row the node is `load undefined`; it is never guessed. |
| **Capacity is checked only with `autoscale.per_instance`.** | No hour is ever over capacity. |
| **Multi-AZ is `ha: multi-az` on the node.** The cost adds `:multi-az` to the instance and the storage itself; write the plain sku (`load.sku.multi_az`). A `spec` entry is only shown (`spec.ha`). | Written in `spec` or in the sku by hand, the storage is priced single-AZ (or, with `ha` too, finds no price). |

## Prices

A price is looked up in three layers, the first that has it winning: the room's `prices/` files, then prices
`jui viz cloud-prices fetch` stored, then the bundled table. Within a layer, the latest row whose `effective` date is
on or before the month is used.

- **Free amounts are taken per scenario.** A scenario is one environment, so environments that share one account
  each take the account's free amount (`cost.free_per_scenario` says so). Internet egress on AWS has the account's
  100 GB a month as one pool across rows and regions (`free.pool: "aws:data-transfer-out"`).
- **A room's row replaces the bundled row whole.** Written without `free`, it drops the bundled free amount
  (`prices.free_dropped`); copy the `free` you mean to keep.
- **The month has its real hours** (720 or 744), not 730.
- **Amounts are USD, on demand**: no reservations, savings plans, discounts or tax.

## Commands

| Command | Exit 0 / 1 / 2 | `--json` |
|---|---|---|
| `jsonui-doc validate infra [root]` | no error / errors / nothing read | problems (code, severity, file, path, short), counts |
| `jsonui-doc validate infra-load [root]` | no error / errors / model or folder unreadable | problems (with node, hour, quantity), scenarios |
| `jsonui-doc validate infra-prices [root]` | no error / errors / folder unreadable | problems, count |
| `jsonui-doc seed infra [root] [-o DIR] [--stdout] [--force]` | written / — / refused | `--stdout` prints the draft |
| `jsonui-doc cost infra [root] [--scenario ID] [--date D] [--by provider\|node]` | simulated / a load file has an error / nothing simulated | the month (or day) as `jui viz` draws it, top nodes, problems, price warnings |
| `jsonui-doc check infra` | clean / mismatch / execution error | each check's status, counts, the results not ok, its report |

Warnings never change the exit code.
