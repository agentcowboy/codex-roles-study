# codex-roles-study

How one operator used a small Codex study to choose workers for building, grounding and review.

This is a historical case study, v0.1, of observations collected on 2026-09-30 and 2026-10-01 with Codex CLI `0.159.2`. It publishes derived numbers and reproducible calculations. The tasks, prompts, outputs, transcripts, hidden tests and judge packets remain private, so readers can reproduce the analysis of the disclosed numbers but cannot reproduce the experiment or independently assess its judgments.

## Run the calculations

```bash
git clone https://github.com/agentcowboy/codex-roles-study.git && cd codex-roles-study && bash ACCEPTANCE
```

Requirements: Bash and Python 3.7+ with its standard library, plus Git for cloning. After cloning, acceptance needs no network, credentials or package installation. A writable temporary directory is required; Python honors `TMPDIR`. Acceptance works by absolute path from another directory and leaves tracked and untracked checkout files unchanged. It validates both data files, checks historical accounting, regenerates the table in temporary storage and runs five mutations through the same validator. Success prints ten lines ending in `ACCEPTANCE PASS`; any failure exits nonzero without that line.

```bash
python3 -B tables.py /tmp/study-results.csv
python3 -B tables.py
python3 -B tables.py --check
```

The first command writes a CSV to the supplied path; the second writes it to stdout; `--check` also compares regeneration with the bundled `results.csv`. The default data directory is relative to `tables.py`, independent of the caller's current directory. Choose an output path outside the checkout to keep it unchanged. [results.csv](results.csv) contains all 113 observed fixture/model/effort cells, including rejected and unjudged attempts.

## Recorded choices

The historical decision rule was: choose the cheapest confirmed cell with three of three outputs accepted and a mean score within `0.10` of the best. Cost means all attempt credits divided by accepted outputs, including credits spent on rejected attempts. Review also requires mean judge-adjusted precision of at least `0.5`. The registered tie breaker was lower median elapsed time; if no cell reached three of three accepted, the fallback was highest acceptance with the role marked unresolved. No cost tie required timing to reproduce these picks; this release discloses no timing data.

Building and grounding used recorded machine scores. **For review, the rule was applied to judge-corrected seeded recall**, calculated from the mean seeded-finding credit of the two judges per output, divided by 15. A recorded count override takes precedence. Corrected precision uses credited seeded findings divided by credited seeded findings plus false findings, averaged over outputs with a nonzero denominator. Valid extra findings are retained separately and excluded from these seeded metrics.

| Rule applied to the hard fixture | Pick | Mean score | Credits per accepted output |
|---|---|---:|---:|
| Building, machine score | `gpt-6-luna xhigh` | 1.000000 | 1.836049 |
| Grounding, machine score | `gpt-6-luna xhigh` | 0.933333 | 0.507714 |
| Review, judge-corrected seeded recall | `gpt-6.1-sol low` | 0.911111 | 5.219163 |

Using machine recall alone for review (with the same judge acceptance and precision gate) would pick **`gpt-6-sol xhigh`**, with mean recall `0.844444` and `12.624047` credits per accepted output. The best confirmed machine recall was `0.866667`, whereas the best corrected recall was `1.000000`. The `0.10` cutoff therefore changes which cheap cell qualifies. The selected corrected-review cell has precision `1.000000` on these three outputs. Judges recorded false findings on only 1 of 43 hard-review outputs, so the precision gate never excluded a cell; this cell's machine candidate precision was 0.71–0.85.

The overrides were separate judgment calls by the operator's coordinating agent, recorded with reasons: for grounding it chose `gpt-6.1-sol low`, whose three hard-fixture outputs matched all 25 keyed answers, rather than the cheaper rule pick that missed one to three answers. For consequential reviews it chose `gpt-6.1-sol xhigh`, with corrected mean recall `0.988889` and `10.954613` credits per accepted output. For building it chose the rule's pick for routine, well-specified work and stronger settings for consequential work. These observations informed local choices; they do not establish the whole current routing policy. The operator adopted role picks later, after a further round that this release excludes.

## Fixtures and method

Each role had one routine and one harder synthetic fixture. These descriptions are newly written summaries, not runnable task specifications.

| Public fixture | Task and primary machine measurement |
|---|---|
| `build-routine-v1` | Repair a small accounting application and add a feature; hidden-test pass fraction. |
| `grounding-routine-v1` | Answer 20 questions from a fictional operations repository; exact keyed-answer fraction. |
| `review-routine-v1` | Review a service change with seeded defects and decoys; recall over nine keyed items and candidate precision. |
| `build-hard-v1` | Implement multi-currency behavior and fix six defects in a larger accounting application; pass fraction over 79 distinct hidden test methods, with visible-suite and protected-file checks recorded separately. |
| `grounding-hard-v1` | Answer 25 multi-hop questions using repository files and history, including configuration precedence and time interpretation; exact keyed-answer fraction. |
| `review-hard-v1` | Review a larger multi-tenant service change with 15 seeded defects, decoys and possible valid unkeyed defects; location/category candidate recall and precision, followed by semantic judging. |

The routine tier gave limited discrimination: build primary was 1.0 throughout, grounding spanned 0.95–1.0, and review recall spanned about 0.78–1.0, so harder fixtures were added. The routine tier was retained and was unjudged. Seven model variants appear in the hard tier; the routine tier contains only three. The observed effort settings are `low`, `medium`, `high`, `xhigh` and selected `max` cells. The resulting allocation is unequal and adaptive.

| Historical stage | Attempts | Treatment |
|---|---:|---|
| `0` | 3 | Routine calibration, machine measurements only |
| `1` | 35 | Routine screen, machine measurements only |
| `H` | 75 | Hard tier, including six calibration attempts, dual-judged |
| `2` | 40 | Selected hard confirmations, dual-judged |
| Total disclosed | 153 | 38 unjudged; 115 dual-judged outputs; 230 verdicts |

The registered advancement rule selected the top three cells per role by acceptance then score, the incumbent (`gpt-5.6-sol high` for building and review; `gpt-5.6-luna medium` for grounding), and up to two cheap contenders with cost at most one-third of the leader's and score within `0.15` of the leader's. Advancing cells received two further runs on the same hard fixture, making `n=3`. Some confirmations started on machine scores before judging finished, to use the available quota. Review cells chosen from machine recall were retained as additional observations when judge-adjusted scores changed advancement. This produced 20 confirmed cells and 40 repeat attempts. The other 93 cells have `n=1`; repeats are adaptive observations of the same task, not independent task samples or a holdout.

The hard outputs were assessed by **two same-family Claude Opus judge streams**, identified here as `a` and `b`. Packets were intended to conceal model and effort. Both `yes` and `with-fixes` count as accepted votes; two such votes accept an output, two `no` votes reject it, and one of each leaves a dispute. Disputes were adjudicated using both verdicts and machine measurements by the operator's coordinating AI agent, which also hosted judge stream `a`; every dispute was resolved to rejection, the stricter of the two votes. `with-fixes` means further work was needed; it does not mean the output was complete.

### Historical credit proxy

All 153 disclosed attempts have recorded known usage. Input includes cached input; reasoning output is already included in output tokens. The frozen formula is:

```text
credits_est = ((input_tokens - cached_input_tokens) * input_rate
               + cached_input_tokens * cached_rate
               + output_tokens * output_rate) / 1_000_000
```

| Model | Input per million | Cached input per million | Output per million |
|---|---:|---:|---:|
| `gpt-6-astra` | 250 | 25 | 1250 |
| `gpt-6-sol` | 50 | 5 | 250 |
| `gpt-6.1-sol` | 50 | 2.5 | 250 |
| `gpt-6-luna` | 2.5 | 0.25 | 12.5 |
| `gpt-5.6-sol` | 100 | 10 | 500 |
| `gpt-5.6-terra` | 50 | 5 | 300 |
| `gpt-5.6-luna` | 5 | 0.5 | 30 |

The labelled `HISTORICAL_RATES` constant in [tables.py](tables.py) implements these weights. Recorded per-attempt credits agree within `0.0000005`, their six-decimal rounding tolerance. These credits are the study's historical token-rate proxy, not money, current prices, measured subscription debits or cash savings. All attempts contribute to cost per accepted output; zero accepted outputs leave that field empty.

## Corrected accounting and judging

The retained experiment corpus has **197 attempts: `197 = 153 + 1 + 43`**. This release selects exactly stages `0`, `1`, `H` and `2`. It excludes one smoke attempt and 43 later-round attempts: 13 calibration and recalibration attempts (`C2`) and 30 screen and repeat attempts (`S2`). Later repeat packets were not additional attempts. Most primary later-round verdicts were not retained, so that round is excluded rather than presented as equivalent evidence.

Among the 115 judged outputs, raw acceptance was **101 accepted / 4 rejected / 10 unresolved**. All ten disputes were adjudicated to rejection: five grounding, three review and two build outputs. Final accounting is **101 accepted / 14 rejected / 0 unresolved**, with the same 38 unjudged routine attempts. [data/corrections.csv](data/corrections.csv) records all ten resolutions; three also carry review-count overrides.

For the 43 hard-review outputs, both judges credited more seeded defects than machine recall multiplied by 15 on **39/43**, and both matched it on **4/43**. None decreased. Correct explanations at alternate locations or categories could evade the machine matcher; valid unkeyed findings were also recorded separately. The raw machine values remain in the data. The ten acceptance adjudications are inter-judge disputes, **not machine-score reversals**. This discrepancy is not proof that judges are better: the private outputs are withheld, the judges share a model family, and both keys and agent adjudication can be wrong.

## Data dictionary

CSV headers are fixed, identifiers and categories are closed enums, and source prose is excluded. Numeric values are written as plain decimals without changing their values or losing precision. An empty field means not applicable, not zero; `machine_secondary` is the one exception, recorded as 0 where not applicable. `results.csv` rounds derived numbers to six decimals.

| `data/attempts.csv` fields | Meaning |
|---|---|
| `attempt_id` | Neutral `a001` through `a153`; stable order by stage (`0`, `1`, `H`, `2`), public fixture, model, effort, then private run timestamp. |
| `fixture_id`, `stage`, `model`, `effort` | The six aliases above, historical phase, model name and effort enum. |
| `result_class` | Recorded `ok` or `error-service`; one service-error attempt still produced a judged output and remains included. |
| `input_tokens`, `cached_input_tokens`, `output_tokens` | Nonnegative integer cumulative usage; cached input cannot exceed total input. |
| `credits_est` | Recorded rounded historical credit estimate. |
| `machine_primary`, `machine_secondary` | Raw primary score described by fixture; secondary is candidate precision for review and zero otherwise. They are never replaced by judge credits. |
| `visible_suite_pass`, `protected_ok` | `true`/`false` build checks; empty for other roles. |
| `flag_clear_results`, `flag_clear_join` | `true` means the scanner reported no flag in that historical snapshot; `false` means flagged. The latter is empty for routine attempts. Both snapshots are retained; 15 judged attempts differ between them. |
| `judge_a_accept`, `judge_b_accept` | Separate raw `yes`, `with-fixes` or `no` votes; empty for routine attempts. |
| `judge_a_overall`, `judge_b_overall` | Separate integer scores from 1 to 10; empty for routine attempts. |
| `judge_a_seeded_found`, `judge_b_seeded_found` | Cardinalities of each judge's credited seeded-defect list, from 0 to 15; only applicable to hard review. |
| `judge_a_extra_found`, `judge_b_extra_found` | Cardinalities of valid unkeyed-finding lists; only applicable to hard review. |
| `judge_a_false_findings`, `judge_b_false_findings` | Nonnegative false-finding counts; only applicable to hard review. |

| `data/corrections.csv` fields | Meaning |
|---|---|
| `attempt_id`, `final_acceptance` | Binds a judged disputed attempt; all ten resolutions are `rejected`. |
| `seeded_found_override`, `false_findings_override`, `seeded_total` | Explicit adjudicated counts for three hard reviews, with seeded total 15; empty for the other seven disputes. |
| `reason_code` | Newly written enums: `review_coverage_shortfall`, `answer_precedence_errors`, `completion_claim_gap`. They summarize deficient review coverage, incorrect precedence reasoning, and completion claims unsupported by the delivered changes. |

| `results.csv` fields | Meaning |
|---|---|
| `fixture_id`, `model`, `effort` | Cell key; 38 routine and 75 hard cells, without filtering flagged attempts. |
| `n` | All attempts in that cell, either 1 or 3. |
| `stage0_count`, `stage1_count`, `H_count`, `stage2_count` | Counts by original phase, preserving adaptive repeats. |
| `judged_count` | Number with both judge streams; zero for routine cells. |
| `final_accepted_count` | Accepted outputs after corrections; empty for unjudged cells. |
| `machine_score_mean` | Mean raw primary machine score over all attempts in the cell. |
| `review_recall_corrected`, `review_precision_corrected` | Mean judge-corrected seeded metrics used by the review decision; empty outside hard review. Overrides precede mean judge counts; undefined per-output precision is omitted from its mean. |
| `credits_per_accepted` | Sum of all attempt credits divided by final accepted outputs; empty for zero accepted or unjudged cells. |
| `flagged_results_count`, `flagged_join_count` | Separate counts of `false` observations in each snapshot; inapplicable join snapshots contribute zero. |

Validation rejects extra columns, invalid enums and numbers, duplicate IDs, missing judge streams, corrections attached to non-disputed rows and stale tables. Acceptance's cell counts describe observed accounting; they are not a public proof that the undisclosed experiment was exhaustively extracted.

## Limits and non-claims

This is neither a general ranking nor an unbiased comparison. It does not demonstrate statistical equivalence or superiority. There is one fixture per role and difficulty tier, with one or three attempts per cell; three accepted outputs do not establish a future acceptance rate. The routine tier gave limited discrimination and was unjudged. Unequal model coverage and adaptive selection constrain comparisons.

Isolation was detection only. Models could inspect ancestor instructions and potentially observe other runs; integrity checks examined command text and had false positives. The two flag snapshots are historical scanner observations, not proof of isolation. Equal instructions do not imply equal effect, and inherited operator instructions were a source of interference in the broader experiment. The adjudicating agent also hosted judge stream `a`, so dispute resolution was not independent of both judge streams.

Keys had known defects: the hard-build reference mishandled a daylight-saving transition not covered by its tests, and review match windows/categories missed valid findings, including a real defect overlapping a decoy window. The hard-build machine scores clustered near the ceiling. Judge execution was unequal: one stream largely read build artifacts under restricted execution, while the other often applied patches and ran suites, with some judgments made by reading. Packets had transcript elision and generated-file noise, with disclosed minor cross-packet filename exposure and shared scratch collisions. Blindness was a procedure with limitations, not a demonstrated guarantee.

The withheld evidence prevents public rechecking of answer keys, output quality and judge semantics. The disclosed table retains one all-attempts view with separate snapshot flag counts; it omits the historical paired flag-filtered view. Timing and concurrency data are omitted, and this release makes no speed claims. It does not cover live-web research, planning, every kind of hard problem or all current worker choices. Re-running the calculations after a model or CLI update does not refresh these historical observations.

Maintenance is best effort. Re-run `bash ACCEPTANCE` after changing data or calculation code; any extension needs its own evidence and explicit scope.

Built with AI coding agents; tested as described in ACCEPTANCE.

MIT licensed; see [LICENSE](LICENSE).
