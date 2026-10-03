#!/usr/bin/env python3
"""Validate disclosed observations and regenerate the historical cell table."""
import argparse
import base64
import csv
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Historical study rates per million tokens: input, cached input, output.
# These are credit-proxy weights, not current prices or invoiced money.
HISTORICAL_RATES = {
    "gpt-6-astra": (Decimal("250"), Decimal("25"), Decimal("1250")),
    "gpt-6-sol": (Decimal("50"), Decimal("5"), Decimal("250")),
    "gpt-6.1-sol": (Decimal("50"), Decimal("2.5"), Decimal("250")),
    "gpt-6-luna": (Decimal("2.5"), Decimal("0.25"), Decimal("12.5")),
    "gpt-5.6-sol": (Decimal("100"), Decimal("10"), Decimal("500")),
    "gpt-5.6-terra": (Decimal("50"), Decimal("5"), Decimal("300")),
    "gpt-5.6-luna": (Decimal("5"), Decimal("0.5"), Decimal("30")),
}
# Frozen data SHA-256 digests, encoded in base64.
FROZEN_DATA_SHA256 = {
    "data/attempts.csv": "pkxI0dheLimVGK3k3lwEaVUHZ6ExcnFh/CR2AhNFb08=",
    "data/corrections.csv": "szd6hgcvGiWwrzanC0RIKqZI3SD/kxPp0jj4m7O44Fo=",
}
ATTEMPT_FIELDS = (
    "attempt_id,fixture_id,stage,model,effort,result_class,input_tokens,"
    "cached_input_tokens,output_tokens,credits_est,machine_primary,machine_secondary,"
    "visible_suite_pass,protected_ok,flag_clear_results,flag_clear_join,"
    "judge_a_accept,judge_a_overall,judge_a_seeded_found,judge_a_extra_found,"
    "judge_a_false_findings,judge_b_accept,judge_b_overall,judge_b_seeded_found,"
    "judge_b_extra_found,judge_b_false_findings"
).split(",")
CORRECTION_FIELDS = (
    "attempt_id,final_acceptance,seeded_found_override,false_findings_override,"
    "seeded_total,reason_code"
).split(",")
RESULT_FIELDS = (
    "fixture_id,model,effort,n,stage0_count,stage1_count,H_count,stage2_count,"
    "judged_count,final_accepted_count,machine_score_mean,review_recall_corrected,"
    "review_precision_corrected,credits_per_accepted,flagged_results_count,"
    "flagged_join_count"
).split(",")
FIXTURES = {
    role + "-" + tier + "-v1"
    for role in ("build", "grounding", "review")
    for tier in ("routine", "hard")
}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
REASONS = {"review_coverage_shortfall", "answer_precedence_errors", "completion_claim_gap"}
VOTES = {"yes", "with-fixes", "no"}
ALLOWED = {"yes", "with-fixes"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_csv(path, fields):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == fields, path.name + ": fixed header mismatch")
        rows = list(reader)
    require(all(set(row) == set(fields) and None not in row.values() for row in rows),
            path.name + ": malformed row")
    return rows


def number(value, label, integer=False, ceiling=None):
    try:
        require(bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value)),
                label + ": invalid numeric syntax")
        parsed = Decimal(value)
        require(parsed.is_finite() and parsed >= 0, label + ": invalid number")
        if integer:
            require(parsed == parsed.to_integral_value(), label + ": expected integer")
        if ceiling is not None:
            require(parsed <= ceiling, label + ": out of range")
        return parsed
    except InvalidOperation:
        raise ValueError(label + ": invalid number")


def raw_status(row):
    if row["stage"] not in {"H", "2"}:
        return "unjudged"
    votes = [row["judge_" + j + "_accept"] in ALLOWED for j in ("a", "b")]
    return "accepted" if all(votes) else "rejected" if not any(votes) else "unresolved"


def review_counts(row, correction):
    if correction:
        return (Decimal(correction["seeded_found_override"]),
                Decimal(correction["false_findings_override"]))
    return tuple(sum(Decimal(row["judge_" + j + "_" + field]) for j in ("a", "b")) / 2
                 for field in ("seeded_found", "false_findings"))


def validate(root):
    attempts = read_csv(root / "data/attempts.csv", ATTEMPT_FIELDS)
    corrections = read_csv(root / "data/corrections.csv", CORRECTION_FIELDS)
    seen = set()
    for row in attempts:
        identity = row["attempt_id"]
        require(bool(re.fullmatch(r"a[0-9]{3}", identity)), "invalid attempt ID")
        require(identity not in seen, "duplicate attempt ID")
        seen.add(identity)
        require(row["fixture_id"] in FIXTURES, "invalid fixture enum")
        require(row["stage"] in {"0", "1", "H", "2"}, "invalid stage enum")
        hard = row["stage"] in {"H", "2"}
        review = row["fixture_id"].startswith("review-")
        build = row["fixture_id"].startswith("build-")
        require(("-hard-" in row["fixture_id"]) == hard, "fixture/stage mismatch")
        require(row["model"] in HISTORICAL_RATES, "invalid model enum")
        require(row["effort"] in EFFORTS, "invalid effort enum")
        require(row["result_class"] in {"ok", "error-service"}, "invalid result enum")
        for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
            number(row[field], field, integer=True)
        incoming, cached, outgoing = (Decimal(row[field]) for field in
                                     ("input_tokens", "cached_input_tokens", "output_tokens"))
        require(cached <= incoming, "cached input exceeds input")
        recorded = number(row["credits_est"], "credits_est")
        rates = HISTORICAL_RATES[row["model"]]
        calculated = ((incoming - cached) * rates[0] + cached * rates[1]
                      + outgoing * rates[2]) / 1_000_000
        require(abs(recorded - calculated) <= Decimal("0.0000005"), "credit rounding mismatch")
        for field in ("machine_primary", "machine_secondary"):
            number(row[field], field, ceiling=1)
        for field in ("visible_suite_pass", "protected_ok"):
            require(row[field] in ({"true", "false"} if build else {""}),
                    field + ": invalid applicability or enum")
        require(row["flag_clear_results"] in {"true", "false"}, "invalid results flag")
        require(row["flag_clear_join"] in ({"true", "false"} if hard else {""}),
                "invalid join flag applicability")
        for judge in ("a", "b"):
            prefix = "judge_" + judge + "_"
            fields = [prefix + field for field in
                      ("accept", "overall", "seeded_found", "extra_found", "false_findings")]
            if not hard:
                require(all(row[field] == "" for field in fields), "unjudged row has judge data")
                continue
            require(row[prefix + "accept"] in VOTES, "missing or invalid judge vote")
            overall = number(row[prefix + "overall"], "judge overall", integer=True, ceiling=10)
            require(overall >= 1, "judge overall below one")
            for suffix in ("seeded_found", "extra_found", "false_findings"):
                if review:
                    number(row[prefix + suffix], prefix + suffix, integer=True,
                           ceiling=15 if suffix == "seeded_found" else None)
                else:
                    require(row[prefix + suffix] == "", "non-review row has review counts")
    require(seen == {"a%03d" % i for i in range(1, 154)}, "attempt ID set mismatch")
    by_id = {row["attempt_id"]: row for row in attempts}
    bound = {}
    for correction in corrections:
        identity = correction["attempt_id"]
        require(identity in by_id and identity not in bound, "unknown or duplicate correction ID")
        row = by_id[identity]
        require(raw_status(row) == "unresolved", "correction must bind a judged disputed row")
        require(correction["final_acceptance"] == "rejected", "invalid final acceptance enum")
        require(correction["reason_code"] in REASONS, "invalid reason code")
        review = row["fixture_id"] == "review-hard-v1"
        expected_reason = ("review_coverage_shortfall" if review else
                           "completion_claim_gap" if row["fixture_id"].startswith("build-")
                           else "answer_precedence_errors")
        require(correction["reason_code"] == expected_reason, "reason/fixture mismatch")
        for field in ("seeded_found_override", "false_findings_override", "seeded_total"):
            if review:
                number(correction[field], field, integer=True,
                       ceiling=15 if field != "false_findings_override" else None)
            else:
                require(correction[field] == "", "non-review count override")
        if review:
            require(correction["seeded_total"] == "15", "wrong seeded total")
        bound[identity] = correction
    require(set(bound) == {r["attempt_id"] for r in attempts if raw_status(r) == "unresolved"},
            "missing adjudication")
    require(len(bound) == 10, "correction count mismatch")
    return attempts, bound


def final_status(row, corrections):
    correction = corrections.get(row["attempt_id"])
    return correction["final_acceptance"] if correction else raw_status(row)


def average(values):
    return sum(values) / len(values)


def render(attempts, corrections):
    groups = defaultdict(list)
    for row in attempts:
        groups[(row["fixture_id"], row["model"], row["effort"])].append(row)
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(RESULT_FIELDS)
    for key, rows in sorted(groups.items()):
        phases = Counter(r["stage"] for r in rows)
        judged = sum(raw_status(r) != "unjudged" for r in rows)
        accepted = sum(final_status(r, corrections) == "accepted" for r in rows)
        recall = precision = ""
        if key[0] == "review-hard-v1":
            counts = [review_counts(r, corrections.get(r["attempt_id"])) for r in rows]
            recall = "%.6f" % average([found / 15 for found, false in counts])
            precisions = [found / (found + false) for found, false in counts if found + false]
            precision = "%.6f" % average(precisions) if precisions else ""
        cost = sum(Decimal(r["credits_est"]) for r in rows)
        writer.writerow([
            *key, len(rows), phases["0"], phases["1"], phases["H"], phases["2"],
            judged, accepted if judged else "",
            "%.6f" % average([Decimal(r["machine_primary"]) for r in rows]),
            recall, precision, "%.6f" % (cost / accepted) if accepted else "",
            sum(r["flag_clear_results"] == "false" for r in rows),
            sum(r["flag_clear_join"] == "false" for r in rows),
        ])
    return out.getvalue()


def check_table(root, table):
    require((root / "results.csv").read_bytes() == table.encode("utf-8"),
            "committed results table differs from regeneration")


def advancement(root, attempts, corrections):
    """Reconstruct selection from first hard runs, then compare confirmed cells."""
    cells = read_csv(root / "results.csv", RESULT_FIELDS)
    keys = [(r["fixture_id"], r["model"], r["effort"]) for r in cells]
    require(len(keys) == len(set(keys)), "duplicate results cell")
    confirmed = set()
    for key, row in zip(keys, cells):
        repeats = number(row["stage2_count"], "stage2_count", integer=True)
        if repeats:
            require(repeats == 2 and row["n"] == "3" and row["H_count"] == "1",
                    "invalid confirmation counts")
            confirmed.add(key)
    details = {}
    for role in ("build", "grounding", "review"):
        fixture = role + "-hard-v1"
        rows = [r for r in attempts if r["fixture_id"] == fixture and r["stage"] == "H"]
        require(bool(rows), role + ": missing advancement inputs")
        first = {(r["model"], r["effort"]): r for r in rows}
        require(len(first) == len(rows), role + ": duplicate first hard run")

        def score(row, machine=False):
            if machine or role == "grounding":
                return Decimal(row["machine_primary"])
            if role == "build":
                return average([Decimal(row["judge_" + j + "_overall"])
                                for j in ("a", "b")]) / 10
            return review_counts(row, corrections.get(row["attempt_id"]))[0] / 15

        def select(machine=False):
            ordered = sorted(first, key=lambda key: (
                final_status(first[key], corrections) != "accepted",
                -score(first[key], machine), Decimal(first[key]["credits_est"]), key))
            top = ordered[:3]
            incumbent = ("gpt-5.6-luna", "medium") if role == "grounding" else ("gpt-5.6-sol", "high")
            require(incumbent in first, role + ": missing incumbent")
            leader = first[top[0]]
            cheap = [key for key in ordered
                     if final_status(first[key], corrections) == "accepted"
                     and Decimal(first[key]["credits_est"]) <= Decimal(leader["credits_est"]) / 3
                     and score(leader, machine) - score(first[key], machine) <= Decimal("0.15")][:2]
            return top, incumbent, cheap

        top, incumbent, cheap = select()
        selected = set(top + [incumbent] + cheap)
        extras = set()
        if role == "review":
            machine_top, machine_incumbent, machine_cheap = select(machine=True)
            extras = set(machine_top + [machine_incumbent] + machine_cheap) - selected
        reproduced = {(fixture, *key) for key in selected | extras}
        observed = {key for key in confirmed if key[0] == fixture}
        require(observed == reproduced, role + ": confirmed cells differ from reconstructed advancement")
        details[role] = (top, incumbent, cheap, sorted(extras), len(observed), len(reproduced))
    require(sum(value[4] for value in details.values()) == len(confirmed),
            "confirmation outside hard roles")
    return details


def print_advancement(details):
    def names(keys):
        return ",".join(model + "/" + effort for model, effort in keys) or "none"

    for role, (top, incumbent, cheap, extras, confirmed, reproduced) in details.items():
        print("ADVANCEMENT role=%s top=%s incumbent=%s cheap=%s extras=%s confirmed=%d reproduced=%d" %
              (role, names(top), names([incumbent]), names(cheap), names(extras), confirmed, reproduced))
    print("ADVANCEMENT confirmed=%d reproduced=%d" %
          (sum(value[4] for value in details.values()), sum(value[5] for value in details.values())))


def negative_controls(root, scratch):
    labels = ("extra-column", "duplicate-id", "missing-judge", "moved-adjudication", "changed-table",
              "changed-non-table-cell", "dropped-confirmation")
    for label in labels:
        target = scratch / label
        shutil.copytree(str(root / "data"), str(target / "data"))
        shutil.copyfile(str(root / "results.csv"), str(target / "results.csv"))
        attempts = read_csv(target / "data/attempts.csv", ATTEMPT_FIELDS)
        corrections = read_csv(target / "data/corrections.csv", CORRECTION_FIELDS)
        fields = ATTEMPT_FIELDS[:]
        if label == "extra-column":
            fields.append("unexpected")
            for row in attempts:
                row["unexpected"] = "1"
        elif label == "duplicate-id":
            attempts[1]["attempt_id"] = attempts[0]["attempt_id"]
        elif label == "missing-judge":
            next(r for r in attempts if r["stage"] == "H")["judge_b_accept"] = ""
        elif label == "moved-adjudication":
            corrections[0]["attempt_id"] = next(
                r["attempt_id"] for r in attempts if raw_status(r) == "accepted")
        elif label == "changed-non-table-cell":
            row = next(r for r in attempts if r["stage"] == "H")
            row["judge_a_overall"] = "9" if row["judge_a_overall"] == "10" else "10"
        elif label == "dropped-confirmation":
            table = read_csv(target / "results.csv", RESULT_FIELDS)
            table.remove(next(r for r in table if r["stage2_count"] == "2"))
            write_csv(target / "results.csv", RESULT_FIELDS, table)
        else:
            table = read_csv(target / "results.csv", RESULT_FIELDS)
            table[0]["n"] = "2"
            write_csv(target / "results.csv", RESULT_FIELDS, table)
        write_csv(target / "data/attempts.csv", fields, attempts)
        write_csv(target / "data/corrections.csv", CORRECTION_FIELDS, corrections)
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--root", str(target),
             "--check-frozen" if label == "changed-non-table-cell" else
             "--advancement" if label == "dropped-confirmation" else "--check"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        require(result.returncode == 1, label + ": negative control did not go RED")
        if label == "changed-non-table-cell":
            require("attempts.csv: frozen SHA-256 mismatch" in result.stderr,
                    label + ": frozen-data check was not the rejection reason")
        elif label == "dropped-confirmation":
            require("confirmed cells differ from reconstructed advancement" in result.stderr,
                    label + ": advancement check was not the rejection reason")
    return labels


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def check_frozen_data(root):
    for name, pinned in FROZEN_DATA_SHA256.items():
        observed = base64.b64encode(hashlib.sha256((root / name).read_bytes()).digest()).decode("ascii")
        require(observed == pinned, Path(name).name + ": frozen SHA-256 mismatch")


def acceptance(root, attempts, corrections, table):
    check_frozen_data(root)
    advanced = advancement(root, attempts, corrections)
    stages = Counter(r["stage"] for r in attempts)
    require(stages == {"0": 3, "1": 35, "H": 75, "2": 40}, "stage accounting mismatch")
    raw = Counter(raw_status(r) for r in attempts)
    final = Counter(final_status(r, corrections) for r in attempts)
    require(raw == {"accepted": 101, "rejected": 4, "unresolved": 10, "unjudged": 38},
            "raw accounting mismatch")
    require(final == {"accepted": 101, "rejected": 14, "unjudged": 38}, "final accounting mismatch")
    cells = list(csv.DictReader(io.StringIO(table)))
    require(len(cells) == 113 and Counter(r["n"] for r in cells) == {"1": 93, "3": 20},
            "cell accounting mismatch")
    require(sum(r["fixture_id"].endswith("routine-v1") for r in cells) == 38,
            "routine cell accounting mismatch")
    reviews = [r for r in attempts if r["fixture_id"] == "review-hard-v1"]
    higher = unchanged = 0
    for row in reviews:
        machine = Decimal(row["machine_primary"]) * 15
        counts = [Decimal(row["judge_" + j + "_seeded_found"]) for j in ("a", "b")]
        if all(value - machine > Decimal("0.000000000001") for value in counts):
            higher += 1
        elif all(abs(value - machine) <= Decimal("0.000000000001") for value in counts):
            unchanged += 1
        else:
            raise ValueError("unexpected review correction pattern")
    require((len(reviews), higher, unchanged) == (43, 39, 4), "review accounting mismatch")
    require(sum(bool(c["seeded_total"]) for c in corrections.values()) == 3,
            "count override accounting mismatch")
    judged = sum(r["stage"] in {"H", "2"} for r in attempts)
    require(judged == 115, "judge accounting mismatch")
    with tempfile.TemporaryDirectory(prefix="study-check-") as temp:
        scratch = Path(temp)
        regenerated = scratch / "results.csv"
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                                 "--root", str(root), str(regenerated)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(result.returncode == 0, "temporary regeneration failed")
        require(regenerated.read_bytes() == (root / "results.csv").read_bytes(),
                "temporary regeneration differs")
        labels = negative_controls(root, scratch)
    print("DATA attempts=%d stage0=%d stage1=%d H=%d stage2=%d" %
          (len(attempts), stages["0"], stages["1"], stages["H"], stages["2"]))
    print("JUDGES outputs=%d verdicts=%d missing=0 duplicates=0" % (judged, 2 * judged))
    for title, counts in (("RAW", raw), ("FINAL", final)):
        print("%s accepted=%d rejected=%d unresolved=%d unjudged=%d" %
              (title, counts["accepted"], counts["rejected"], counts["unresolved"], counts["unjudged"]))
    print("CELLS cells=%d n1=93 n3=20" % len(cells))
    print("CORRECTIONS acceptance=%d review-higher-both=%d/43 review-unchanged-both=%d/43" %
          (len(corrections), higher, unchanged))
    print("CREDITS rows=%d within-rounding=yes" % len(attempts))
    print("TABLES rows=%d regenerated=equal" % len(cells))
    print("ADVANCEMENT confirmed=%d reproduced=%d" %
          (sum(value[4] for value in advanced.values()), sum(value[5] for value in advanced.values())))
    print("NEGATIVE_CONTROLS " + " ".join(label + "=RED" for label in labels))
    print("ACCEPTANCE PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", help="output CSV path; default stdout")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--check", action="store_true", help="also validate the committed table")
    parser.add_argument("--check-frozen", action="store_true",
                        help="validate the committed table and frozen data without running controls")
    parser.add_argument("--advancement", action="store_true",
                        help="reconstruct advancement and compare with confirmed table cells")
    parser.add_argument("--acceptance", action="store_true", help="run the historical accounting and controls")
    args = parser.parse_args()
    try:
        attempts, corrections = validate(args.root)
        table = render(attempts, corrections)
        if args.check or args.check_frozen or args.acceptance:
            check_table(args.root, table)
        if args.check_frozen:
            check_frozen_data(args.root)
        if args.acceptance:
            acceptance(args.root, attempts, corrections, table)
        elif args.advancement:
            print_advancement(advancement(args.root, attempts, corrections))
        elif not (args.check or args.check_frozen):
            if args.output:
                Path(args.output).write_bytes(table.encode("utf-8"))
            else:
                sys.stdout.write(table)
        return 0
    except (ValueError, OSError) as exc:
        print("validation failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
