---
name: independent-review
description: "Run one supervised static review with fresh reviewer subagents against staged changes, a commit or range, one task or epic, or a roadmap-independent investigation. Use when the user explicitly invokes /aquarium:independent-review and asks for an independent verdict without remediation."
---

# Independent Review

Run the canonical Aquarium review contract with one or more fresh reviewer subagents in the current worktree. The execution backend is the host's own `Agent` tool rather than Orca, so a reviewer shares the coordinator's model but starts from a context that has not seen the coordinator's reasoning; claim that guarantee and no more. This is a standalone review workflow, not the Mulgae phase owned by `/aquarium:task-review`. Use `/aquarium:orca-review` only when the user wants a supported external provider CLI.

## Load the Contracts

1. Read [review-contract.md](../../references/review-contract.md) completely. It owns target selection, dirty-state handling, consent, static-review limits, and the result envelope.
2. Resolve this skill directory and use `scripts/inspect_review_target.py` from it. Do not copy or approximate the inspector contract.

## Establish the Request

1. Resolve one current Git root and classify the request as `staged`, `commit`, `range`, `task`, `epic`, or `special request`.
2. For a task or epic, inspect its roadmap and linked authority first. Select a Git target automatically only when the authority identifies one unambiguous staged candidate, commit, or range; otherwise ask the user to choose among the concrete candidates.
3. For a special request, establish the exact question, then always ask the user to confirm staged, `HEAD`, one commit, or one explicit two-dot or three-dot range.
4. Inspect HEAD, branch, upstream, staged, unstaged, untracked, ignored, and conflicted state. Resolve any staged-target dirty decision exactly as the shared contract requires. Never review dirty working-tree content as a target.
5. Run the target inspector after all required choices or staging operations. Bind its complete JSON result and the resolved authority paths to every reviewer specification.

Explicit invocation with an exact target and a fresh reviewer authorizes the source transmission needed for this review. Do not ask for duplicate approval unless the target, included paths, reviewer, or execution scope changes. The workflow authorizes no source edits, tests, builds, generators, formatters, linters, provider reviews, commits, pushes, publication, or remediation. The only permitted mutation is exact-path staging that the user separately approved under the dirty decision.

## Dispatch Fresh Reviewers

Dispatch at least one reviewer subagent through the host's `Agent` tool, and dispatch several when the target spans distinct review dimensions. Use the read-only `Explore` subagent type for every reviewer. Give each reviewer a distinct lens — requirements conformance, implementation correctness, test and coverage adequacy — so that additional reviewers buy coverage rather than repetition. Launch them in a single message so they run concurrently, and record which lens each one received.

State the read-only constraint in each specification as well, so it stands as an explicit requirement rather than relying on the subagent type alone.

Each specification must include:

- the absolute repository root, target-inspector result, review focus, and authority paths;
- exact included and excluded state, including the same-user visibility disclosure when dirty content is excluded;
- instructions to use index blobs for staged targets and resolved commit blobs for commit, range, or `HEAD` targets rather than later working-tree copies;
- the static-only restrictions and `runtime unverified` requirement from the shared contract;
- the required finding fields and exact `APPROVE` condition;
- the user's test-status statement only as context, never as independently verified evidence.

Do not seed a reviewer with suspected findings or intended fixes. Require each reviewer to modify no files and leave its complete review in its final response.

## Fail Closed on Dispatch

1. Stop with the exact gap when the subagent mechanism is unavailable, when a dispatch fails, or when a reviewer returns no usable output.
2. Never substitute the coordinator's own review, a chat delegation, an ad hoc terminal, or a raw agent CLI for a dispatched reviewer. The coordinator has already reasoned about this target and cannot review it independently.
3. An operational failure is not an `APPROVE` result.

## Supervise and Adjudicate

Wait for each dispatched reviewer to report rather than predicting its result, and give the user a progress update while waiting. Disclose and record one cumulative supervision budget, using 30 minutes unless the user explicitly selected another duration. When a reviewer returns nothing usable within the recorded budget, or a dispatch fails, stop waiting, leave any partial result intact, and report the review as operationally incomplete with the exact dispatch status. Further waiting, re-dispatch, or replacement requires an explicit user request; never retry, cancel, or substitute a reviewer automatically. Keep technical review status separate from dispatch status, so a reviewer that never ran is never read as a clean verdict. Answer reviewer questions only from established repository facts; ask the user when an answer requires product intent or wider authority.

After the reviewers report, independently check every finding against the exact target, authority, production callers, persistence and concurrency boundaries, and existing tests without running checks or changing files. Classify findings as Valid, Invalid, or Needs confirmation under the shared result contract. A functionality claim that still requires execution remains `runtime unverified`.

When several reviewers ran, merge overlapping findings once and keep disagreements visible. A finding one reviewer raised and another contradicted is a needs-confirmation item with both positions stated, never an averaged verdict.

Return the complete shared result envelope, identify the reviewer subagents and the lens each received, and report separate dispatch and reviewer status. Wrong scope, modified files, missing output, or a failed dispatch prevents a clean verdict.
