# firebud_multiagent_bug_hunter — architecture and methodology

## Overview

firebud_multiagent_bug_hunter is our self-developed multi-agent cluster and
harness system built around an LLM. It runs a security-verification campaign
on the provided design tree: a set of specialized agents (audit, proof-of-
concept execution, evidence packaging, report drafting, final review) operate
under work orders, while the harness around them is fully deterministic
(orchestration, assertions, verdict tokens, re-runs).

The division of labor is deliberate:

- **LLM agents own exploration and judgment-heavy work**: choosing audit
  targets, forming hypotheses about security-relevant design behavior,
  writing testbenches and on-device tests, drafting the submission report.
- **The harness owns verification and is fully deterministic**: fixed
  numeric assertions, attack-arm/secure-arm causal controls, fresh-directory
  re-runs, verdict tokens printed as the last stdout line, acceptance runs
  in a judge-equivalent container environment.
- **The LLM never judges pass/fail.** Every PASS/FAIL verdict is produced
  by a deterministic test that a human can re-run.
- **A human reviews every package before submission.** Submission itself is
  always a manual step performed by the team.

## Agent roles

| Role | Responsibility |
|---|---|
| auditor | attacker-seat deep audit of a target region; registers candidate findings with a complete attack narrative |
| poc-planner | candidate queue, work-order authoring, wave scheduling |
| poc-runner | turns an attack narrative into a machine-judged PoC (testbench or on-device test), reports a four-valued verdict |
| adjudicator | submission-value adjudication against the official scoring rules; root-cause clustering |
| bug-planner | per-bug chain orchestration (report → verify → exploit → check) |
| reporter | drafts the 27-question submission report |
| verifier | packages PoC evidence, independently re-runs it, re-checks the full attacker chain |
| exploiter | builds the exploit package in the form required for the attacker class |
| checker | judge-perspective final review: replay in a clean environment, scoring simulation |
| controller | campaign-level scheduling, round focus, failure recovery |

## Campaign discipline enforced by the harness

1. **Attacker chain standard (seven gates).** Every candidate must be
   expressed as a complete attacker narrative before it can enter the
   validation chain: named adversary class, starting state equal to the
   delivered state of the booted device, an established security boundary
   being crossed, trigger steps within the attacker's real capability, and
   an observable harm to a protected asset.
2. **Form matching.** Software-class exploits are delivered as on-device
   tests (Bazel-built device tests); physical-class exploits as an attack
   flow plus a simulation testbench with fidelity and fault-injection
   locality arguments.
3. **Deterministic verdicts.** PoC and exploit packages expose exactly two
   make targets; the verdict token is the last stdout line and the run
   always exits 0; any exit without a token is treated as the most severe
   incident.
4. **Causal controls.** Where structurally applicable, a dual-arm build
   (attack arm vs secure arm) demonstrates that the observed behavior is
   caused by the specific defect under test.
5. **Acceptance track.** Final evidence is produced by re-running the
   package in a judge-equivalent container (same tree, Verilator 4.210,
   fresh scratch directory).

## LLM configuration

- CLI: Claude Code {{CLAUDE_VERSION}}
- Model: {{MODEL}} (accessed via API, online)
- Per-session usage is recorded in `tokens.txt` (input tokens including
  prompt-cache reads, output tokens, totals). The prompts and full session
  transcripts for this bug's discovery and validation chain are archived
  under `prompts/` and `responses/`.

## Re-running with your own key

The harness scripts in `scripts/` are the campaign orchestration (pipeline
definitions), the lint battery, the judge-replay script, and the evidence
collector. To re-run the discovery process with your own API key, set your
key in the environment used by the `claude` CLI and run the campaign
orchestration entry point (`flow run`) with the pipeline definitions in
`scripts/`; each agent session then executes with your credentials. The
 deterministic verification steps (make packages, judge-replay) require no
API key at all.

## Session map for this bug

See `README.md` in this directory for the exact chain of sessions that led
to this bug: which session formed the hypothesis, which sessions validated
it, and where each piece of evidence lives.
