# Multi-Agent Task Resolution — Evaluation

Runs every scenario in `scenarios.json` through the real, compiled LangGraph
workflow (`run_case`) — real Bedrock calls, real Planner/Investigation/
Resolution agents, the deterministic Reflection gate, real deterministic
tools — and reports how closely the system's actual behavior matches the
expected outcome for each scenario.

## How it works

- `run_evaluation.py` creates a fresh, self-contained **SQLite** database on
  every run (in memory) and seeds it with a fixed set of customers, orders,
  and policies (`_seed_fixtures`). Order delivery dates are computed relative
  to the current time (e.g. "2 days ago", "30 days ago") so "valid" vs.
  "outside the resolution window" scenarios stay correct no matter when the
  suite is run — no dependency on the shared dev Postgres database or on
  calendar dates going stale.
- One scenario (`SC-024`, `missing_delivery_already_resolved`) targets a
  pre-seeded `Case` that starts out already `resolved`, to prove the system
  leaves a closed case alone on a duplicate request.
- For each scenario, a `Case` row is created (unless `case_id` is given),
  then run through `run_case()` — the same compiled LangGraph the API and
  frontend use. No agent or tool logic is duplicated.

## Running it

The script imports the backend's `app` package and needs `backend/.env` to
resolve, so run it with the backend's virtualenv **from the `backend/`
directory**:

```bash
cd backend
.venv/bin/python ../evaluation/run_evaluation.py
```

Optional flags:

```bash
.venv/bin/python ../evaluation/run_evaluation.py --scenarios ../evaluation/scenarios.json --output ../evaluation/results.json
```

This makes real Bedrock Mantle API calls — one run of the default 33
scenarios takes roughly 1–2 minutes and is not free.

## Metrics

Written to `results.json` alongside the per-scenario detail:

| Metric | Meaning |
|---|---|
| `issue_classification_accuracy` | Fraction where `predicted_issue_type == expected_issue_type` |
| `resolution_accuracy` | Fraction where `predicted_resolution == expected_resolution` |
| `final_status_accuracy` | Fraction where `predicted_status == expected_status` |
| `escalation_accuracy` | Fraction where "did we escalate?" (predicted vs. expected) agree, regardless of the other fields |
| `action_success_rate` | Fraction where the deterministic tool call (`resolution_action`/`escalate_case`) itself reported `success: true` |
| `total_passed` / `total_scenarios` | Scenarios where issue type, resolution, and status all matched expectations |
| `average_latency_seconds` | Mean wall-clock time per scenario through the full graph |

A scenario counts as `passed` only if all three of `issue_type`,
`resolution`, and `status` match. `escalation_accuracy` is looser
(escalate/didn't-escalate agreement only) since it's useful to see even when
the specific resolution reasoning didn't line up.

## Scenario coverage (33 total)

| Category | Count | Scenario IDs |
|---|---|---|
| Damaged order — valid refund | 2 | SC-001, SC-003 |
| Damaged order — valid replacement | 2 | SC-002, SC-004 |
| Damaged order — outside resolution window | 2 | SC-005, SC-006 |
| Damaged order — missing order info | 4 | SC-007–SC-010 |
| Wrong item — valid replacement | 3 | SC-011–SC-013 |
| Wrong item — wrong customer | 2 | SC-014, SC-015 |
| Wrong item — outside policy window | 2 | SC-016, SC-017 |
| Wrong item — disallowed action requested | 1 | SC-018 |
| Missing delivery — valid refund | 4 | SC-019, SC-021, SC-024*, SC-025 |
| Missing delivery — invalid order | 2 | SC-022, SC-023 |
| Missing delivery — already resolved case | 1 | SC-024 |
| Unsupported request | 3 | SC-026, SC-027, SC-033 |
| Incomplete information | 3 | SC-028, SC-029, SC-032 |
| Invalid customer | 2 | SC-030, SC-031 |

\* SC-024 is counted once (already-resolved category); listed twice above
only to show it's also a refund-policy case.

**Note on "missing policy":** the spec's safety category lists this
alongside invalid customer / unsupported request / incomplete information.
In this system a policy always exists for all three supported issue types
(`damaged_order`, `missing_delivery`, `wrong_item`) — that's a deliberate
invariant, not an oversight — so a genuine "no policy found" condition can't
be reached through customer-facing message content; it would require an
admin deleting a policy row out from under a live request. The closest
message-driven equivalent is an unclassifiable/unsupported request, which
takes the same escalation path and is covered by the `unsupported_request`
and `incomplete_information` scenarios above.

## Latest results

See `results.json` for the full per-scenario breakdown. Last run:

- **33/33** scenarios executed successfully (no crashes)
- **31/33** passed all three checks (issue type, resolution, status)
- **100%** issue classification accuracy
- **~94%** resolution accuracy — the misses are genuine model
  disagreements (e.g. choosing REFUND when the customer asked for a
  REPLACEMENT and the policy allowed both), not harness bugs
- **~97%** final status and escalation accuracy
- ~2.3s average latency per scenario (three real Bedrock calls each: Planner,
  Investigation, and — when Reflection allows it to continue — Resolution)

## Tests

`test_run_evaluation.py` covers scenario loading, metric calculation, and
result generation, using injected fake Bedrock clients (no real API calls,
no dependency on scenario wording matching real model behavior). Run from
the backend virtualenv:

```bash
cd backend
.venv/bin/python -m pytest ../evaluation/test_run_evaluation.py
```
