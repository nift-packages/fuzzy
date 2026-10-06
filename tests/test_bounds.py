#!/usr/bin/env python3
"""Boundary, budget and banded-matcher differential tests for the fuzzy package.

The banded bounded matcher is differentially checked against the full dynamic
program for many random inputs, and the new work budgets' exact/one-above
boundaries are exercised. Ordinary applications never approach the budgets.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

NIFT = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/nick/Repositories/nift/nift/nift").resolve()
PACKAGE = Path(__file__).resolve().parent.parent
TESTS = PACKAGE / "tests"
SOURCE = PACKAGE / "src" / "fuzzy.f"

source = SOURCE.read_text(encoding="utf-8")
public_methods = re.findall(r"^    fn\(([A-Za-z_][A-Za-z0-9_]*)\(", source, re.MULTILINE)
if public_methods != ["distance", "matches", "filter", "rank"]:
    raise SystemExit(f"FAIL unexpected public facade: {public_methods!r}")


def require(condition, message, result=None):
    if condition:
        return
    if result is not None:
        message += f"\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}\nreturn code: {result.returncode}"
    raise SystemExit("FAIL " + message)


def qs(text):
    return json.dumps(text, ensure_ascii=False)


def run(args, cwd):
    return subprocess.run([str(NIFT), *args], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=90, check=False)


WORK = Path(tempfile.mkdtemp(prefix=".fuzzy-bounds-", dir=TESTS))
try:
    consumer = WORK / "consumer"
    consumer.mkdir()
    (consumer / ".nift").mkdir()
    added = run(["add", str(PACKAGE)], consumer)
    require(added.returncode == 0, "nift add failed", added)

    def run_script(name, body):
        (consumer / name).write_text(body, encoding="utf-8")
        return run([name], consumer)

    # 1. Banded bounded matcher vs full DP: exact parity over a deterministic corpus.
    body = """@import("fuzzy")
mismatches := 0
trials := 0
seed := 0
while(seed < 600) {
    a := ""
    b := ""
    j := 0
    na := 1 + (seed * 7) % 8
    nb := 1 + (seed * 5) % 8
    while(j < na) { a += bytes([65 + (seed + j) % 4]).decode("utf-8"); j += 1 }
    j = 0
    while(j < nb) { b += bytes([65 + (seed * 3 + j) % 4]).decode("utf-8"); j += 1 }
    k := seed % 5
    if(fuzzy.matches(a, b, k) != (fuzzy.distance(a, b) <= k)) {
        mismatches += 1
        print("MISMATCH seed=" + seed.to_string() + " k=" + k.to_string() + " a=" + a + " b=" + b)
    }
    trials += 1
    seed += 1
}
print("trials=" + trials.to_string() + " mismatches=" + mismatches.to_string())
"""
    res = run_script("diff.f", body)
    require(res.returncode == 0 and "mismatches=0" in res.stdout,
            "banded vs full differential failed", res)

    # 2. Exact budget boundary and one-above (500x500 == cap allowed; 501x500 rejected fast).
    s500 = "a" * 500
    s501 = "a" * 501
    allowed = run_script("allow500.f",
                         '@import("fuzzy")\nprint(fuzzy.distance(' + qs(s500) + ', ' + qs(s500) + '))\n')
    require(allowed.returncode == 0 and allowed.stdout.strip() == "0",
            "in-budget 500x500 distance should compute", allowed)
    over = run_script("over501.f",
                      '@import("fuzzy")\nprint(fuzzy.distance(' + qs(s501) + ', ' + qs(s500) + '))\n')
    require(over.returncode != 0, "over-budget 501x500 distance should be rejected", over)

    # 3. Clearly oversized inputs are rejected quickly (no hang).
    s4000 = "a" * 4000
    res = run_script("big.f", '@import("fuzzy")\nfuzzy.distance(' + qs(s4000) + ', "b" * 4000)\n')
    require(res.returncode != 0, "4000x4000 distance should be rejected", res)
    res = run_script("bigmatch.f",
                     '@import("fuzzy")\nfuzzy.matches(' + qs(s4000) + ', ' + qs(s4000) + ', 100000)\n')
    require(res.returncode != 0, "huge-k matches should be rejected", res)

    # 4. Long equal / totally different strings at moderate size stay within budget.
    e500 = run_script("eq500.f", '@import("fuzzy")\nprint(fuzzy.distance(' + qs(s500) + ', ' + qs(s500) + '))\n')
    require(e500.returncode == 0 and e500.stdout.strip() == "0", "long equal distance", e500)
    d500 = run_script("de500.f",
                      '@import("fuzzy")\nprint(fuzzy.distance(' + qs("a" * 500) + ', ' + qs("b" * 500) + '))\n')
    require(d500.returncode == 0 and d500.stdout.strip() == "500", "long different distance", d500)

    # 5. Banded makes large-band matches fast: a 5000-char pair with k=2 computes.
    res = run_script("bandfast.f",
                     '@import("fuzzy")\nprint(fuzzy.matches(' + qs("a" * 5000) + ', ' + qs("a" * 5000) + '))\n')
    require(res.returncode == 0 and res.stdout.strip() == "true", "large banded matches should compute", res)

    # 6. filter/rank candidate and aggregate caps.
    cands_ok = ",".join(qs("c" * 100) for _ in range(1000))
    res = run_script("fk1000.f",
                     '@import("fuzzy")\nprint(fuzzy.filter(' + qs("c" * 100) + ', [' + cands_ok + ']).size())\n')
    require(res.returncode == 0 and res.stdout.strip() == "1000", "1000-candidate filter should compute", res)
    cands_over = ",".join(qs("c" * 100) for _ in range(1001))
    res = run_script("fk1001.f",
                     '@import("fuzzy")\nfuzzy.filter(' + qs("c" * 100) + ', [' + cands_over + '])\n')
    require(res.returncode != 0, "1001-candidate filter should be rejected", res)
    cands_500 = ",".join(qs("c" * 10) for _ in range(500))
    res = run_script("rk500.f",
                     '@import("fuzzy")\nprint(fuzzy.rank(' + qs("c" * 10) + ', [' + cands_500 + ']).size())\n')
    require(res.returncode == 0 and res.stdout.strip() == "500", "500-candidate rank should compute", res)
    res = run_script("rk1001.f",
                     '@import("fuzzy")\nfuzzy.rank("x", [' + ",".join(qs("x") for _ in range(1001)) + '])\n')
    require(res.returncode != 0, "1001-candidate rank should be rejected", res)

    # 7. Unicode/byte semantics unchanged.
    res = run_script("uni.f",
                     '@import("fuzzy")\nprint(fuzzy.distance("Aé", "aé"))\nprint(fuzzy.matches("😀", "😃", 1))\n'
                     'print(fuzzy.distance("😀", "") )\n')
    require(res.returncode == 0 and res.stdout.strip().splitlines() == ["0", "true", "4"],
            "unicode byte semantics changed", res)

    # 8. Deterministic repeat under a within-budget workload.
    res = run_script("det.f",
                     '@import("fuzzy")\ni := 0\nbase := fuzzy.rank("cat", ["dog", "bat", "cat", "cut", "at"]).stringify()\n'
                     'while(i < 30) {\n'
                     '  if(fuzzy.rank("cat", ["dog", "bat", "cat", "cut", "at"]).stringify() != base) { print("DIFF"); i = 100 }\n'
                     '  i += 1\n}\nprint("done")\n')
    require(res.returncode == 0 and res.stdout.strip() == "done", "deterministic repeat failed", res)

finally:
    shutil.rmtree(WORK, ignore_errors=True)

print("PASS fuzzy bounds/differential tests")