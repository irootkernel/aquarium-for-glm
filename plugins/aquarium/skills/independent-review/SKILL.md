---
name: independent-review
description: "Run one or more supervised, read-only requirements and code reviews with fresh reviewer subagents in the current worktree, then adjudicate their findings and propose responses without making changes. Use when the user explicitly invokes /aquarium:independent-review with exactly one epic or task and asks to receive the independent review result."
---

# Independent Review

Coordinate one or more fresh read-only reviewer subagents in the current worktree, preserve the current checkout, and independently verify the returned findings before recommending any response. This is a standalone review workflow, not the Mulgae phase owned by `/aquarium:task-review`.

## Establish the Review Contract

1. Require exactly one epic or task identifier and one current Git repository. Resolve the repository root, applicable instruction files, and the authoritative roadmap, requirements, specifications, decisions, and contracts for that identifier.
2. Inspect HEAD, branch, upstream, staged, unstaged, untracked, and conflicted state. Define the exact review snapshot and distinguish target-owned changes from unrelated work. Include committed, staged, and unstaged target code when applicable; never expose unrelated untracked content merely because it is present.
3. Treat the user's statement that tests passed as context. Do not rerun tests, generators, formatters, linters, provider reviews, or other validation commands in either the coordinator or a reviewer.
4. If the target authority or review boundary cannot be established safely, ask one focused question and do not dispatch a reviewer until the ambiguity is resolved.

Explicit invocation authorizes dispatching one or more read-only reviewer subagents in the current worktree. It does not authorize source edits, staging, commits, pushes, worktree creation, destructive actions, Mulgae, or remediation.

## Dispatch Fresh Reviewers

Dispatch at least one reviewer subagent through the host's `Agent` tool, and dispatch several when the target spans distinct review dimensions. Use the read-only `Explore` subagent type for every reviewer. Give each reviewer a distinct lens — requirements conformance, implementation correctness, test and coverage adequacy — so that additional reviewers buy coverage rather than repetition. Launch them in a single message so they run concurrently, and record which lens each one received.

State the read-only constraint in each specification as well, so it stands as an explicit requirement rather than relying on the subagent type alone.

Build each specification from source evidence, including the absolute repository, target identifier, authority paths, exact review snapshot or range, relevant staged and unstaged state, and the fact that tests already passed. Do not include the coordinator's suspected findings or intended fixes.

Require each reviewer to:

- read applicable instructions, requirements, contracts, code, and relevant existing tests;
- remain strictly read-only and run no tests, generators, formatters, linters, or provider reviews;
- report only verified, actionable findings and omit style preferences, speculation, and praise;
- separate production defects from required test, specification, or current-documentation gaps;
- give each finding a severity, exact `path:line`, triggering scenario, violated requirement, impact, and smallest remediation;
- return exactly `APPROVE` when no actionable finding remains;
- leave the detailed review in its final response and report no modified files.

A reviewer subagent shares the coordinator's model, so what this buys is a fresh context that has not seen the coordinator's reasoning, not an independent model. Claim that guarantee and no more. Distinct lenses across several reviewers are what widen coverage.

## Fail Closed on Dispatch

1. Stop with the exact gap when the subagent mechanism is unavailable, when a dispatch fails, or when a reviewer returns no usable output.
2. Never substitute the coordinator's own review, a chat delegation, an ad hoc terminal, or a raw agent CLI for a dispatched reviewer. The coordinator has already reasoned about this target and cannot review it independently.
3. An operational failure is not an `APPROVE` result.

## Supervise and Settle

Before dispatch, disclose and record one cumulative supervision budget, using 30 minutes unless the user explicitly selected another duration. Wait for each dispatched reviewer to report rather than predicting its result, and give the user a progress update while waiting. Answer reviewer questions only from established repository facts; ask the user when an answer requires product intent or wider authority.

When a reviewer returns nothing usable within the recorded budget, or a dispatch fails, stop waiting, leave any partial result intact, and report the review as operationally incomplete with the exact dispatch status. Further waiting, re-dispatch, or replacement requires an explicit user request; never retry, cancel, or substitute a reviewer automatically. An operational failure is not an `APPROVE` result.

Process every returned review in full. Keep technical review evidence and dispatch status as separate statuses, so a reviewer that never ran is never read as a clean verdict.

## Adjudicate the Result

Verify every reviewer finding against the current authority, code, callers, persistence boundaries, and existing tests without changing files or running checks. Classify each item as:

- **Valid**: confirmed and actionable; propose the smallest implementation and regression-coverage response.
- **Invalid**: contradicted by exact evidence; explain the contradiction briefly.
- **Needs confirmation**: plausible but dependent on missing authority or runtime evidence; state the precise evidence needed.

When several reviewers ran, merge overlapping findings once and keep disagreements visible. A finding one reviewer raised and another contradicted is a needs-confirmation item with both positions stated, never an averaged verdict.

Do not implement a proposed response. If every reviewer returned `APPROVE`, first confirm that each examined the intended snapshot and authority, then report that no actionable feedback was found. If output is missing, scope is wrong, or dispatch failed, report the operational gap without a clean verdict.

Return the target and snapshot, how many reviewers ran and with which lens, each reviewer's verdict, adjudicated findings, and recommended responses.
