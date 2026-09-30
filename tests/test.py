#!/usr/bin/env python3
"""Offline integration and contract tests for the fuzzy package."""

import json
import os
import re
import subprocess
import sys
import tempfile


NIFT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "nift")
PACKAGE = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), ".."))
TESTS = os.path.dirname(os.path.abspath(__file__))
WORK_DIRECTORY = tempfile.TemporaryDirectory(prefix=".fuzzy-test-", dir=TESTS)
WORK = WORK_DIRECTORY.name
SOURCE = os.path.join(PACKAGE, "src", "fuzzy.f")


def run(script, cwd):
    return subprocess.run(
        [NIFT, script], cwd=cwd, capture_output=True, text=True, timeout=20
    )


def require(condition, message, detail=""):
    if not condition:
        raise AssertionError(message + (("\n" + detail) if detail else ""))


with open(SOURCE, encoding="utf-8") as source_file:
    package_source = source_file.read()
with open(os.path.join(PACKAGE, "manifest.json"), encoding="utf-8") as manifest_file:
    manifest = json.load(manifest_file)

public_methods = re.findall(r"^    fn\(([A-Za-z_][A-Za-z0-9_]*)\(", package_source, re.MULTILINE)
private_methods = re.findall(r"^    private fn\(([A-Za-z_][A-Za-z0-9_]*)\(", package_source, re.MULTILINE)
exports = re.findall(r"^export\(([^)]+)\)$", package_source, re.MULTILINE)
require(public_methods == ["distance", "matches", "filter", "rank"], "unexpected public facade surface")
require(exports == ["fuzzy"], "package must export only fuzzy")
require(private_methods, "implementation helpers must be private methods")
require(manifest.get("name") == "fuzzy" and manifest.get("entry") == "src/fuzzy.f", "invalid manifest identity")
require(not manifest.get("dependencies"), "fuzzy must have zero package dependencies")

contract = r'''
fn(expect(condition, label)) { if(!condition) { print("FAIL " + label); missing.value } }

expect(fuzzy.distance("kitten", "sitting") == 3, "classic distance")
expect(fuzzy.distance("KITTEN", "kitten") == 0, "ASCII folding")
expect(fuzzy.distance("", "") == 0, "both empty")
expect(fuzzy.distance("abc", "") == 3, "right empty")
expect(fuzzy.distance("", "abc") == 3, "left empty")
expect(fuzzy.distance("é", "e") == 2, "UTF-8 byte distance")
expect(fuzzy.distance("Ä", "ä") == 1, "non-ASCII is not folded")
expect(fuzzy.distance("😀", "") == 4, "emoji byte length")
expect(fuzzy.distance("é", "ê") == 1, "two-byte substitution")
expect(fuzzy.distance("😀", "😃") == 1, "four-byte substitution")
expect(fuzzy.distance("a😀b", "a😃b") == 1, "mixed multibyte substitution")
expect(fuzzy.distance("Aé", "aé") == 0, "ASCII fold beside multibyte")

expect(fuzzy.matches("book", "back"), "default maximum")
expect(!fuzzy.matches("book", "back", 1), "explicit maximum")
expect(fuzzy.matches("same", "SAME", 0), "zero maximum")
expect(fuzzy.matches("ab", "cd"), "default boundary accepted")
expect(!fuzzy.matches("abc", "xyz"), "above default boundary rejected")

filtered := fuzzy.filter("cat", ["cat", "cut", "dog", "CAT", "at"], 1)
expect(filtered.stringify() == "[\"cat\",\"cut\",\"CAT\",\"at\"]", "filter order")
expect(fuzzy.filter("x", []).size() == 0, "empty candidates")

ranked := fuzzy.rank("cat", ["dog", "bat", "cat", "cut", "at", "cat"])
expect(ranked.size() == 6, "rank size")
expect(fuzzy.rank("cat", []).size() == 0, "empty rank")
expect(ranked[0].candidate == "cat" && ranked[0].distance == 0, "best rank")
expect(ranked[1].candidate == "cat" && ranked[1].distance == 0, "duplicate retained")
expect(ranked[2].candidate == "bat" && ranked[3].candidate == "cut" && ranked[4].candidate == "at", "stable ties")
expect(ranked[5].candidate == "dog" && ranked[5].distance == 3, "worst rank")

baseline := ranked.stringify()
i := 0
while(i < 50) {
    expect(fuzzy.rank("cat", ["dog", "bat", "cat", "cut", "at", "cat"]).stringify() == baseline, "repeat determinism")
    i += 1
}
print("PASS contract")
'''

malformed = [
    'fuzzy.distance(1, "a")',
    'fuzzy.distance("a", null)',
    'fuzzy.distance("a")',
    'fuzzy.distance("a", "b", "c")',
    'fuzzy.matches("a")',
    'fuzzy.matches("a", "b", -1)',
    'fuzzy.matches("a", "b", "1")',
    'fuzzy.matches("a", "b", 1, 2)',
    'fuzzy.filter("a", "not-an-array")',
    'fuzzy.filter("a", ["a", 2])',
    'fuzzy.filter("a", [], -1)',
    'fuzzy.filter("a", [], 1, 2)',
    'fuzzy.rank(1, [])',
    'fuzzy.rank("a", [null])',
    'fuzzy.rank("a", [], 1)',
]

try:
    direct_source = '@import("../../src/fuzzy.f")\n' + contract
    with open(os.path.join(WORK, "direct.f"), "w", encoding="utf-8") as output:
        output.write(direct_source)
    direct = run("direct.f", WORK)
    require(direct.returncode == 0 and direct.stdout.strip() == "PASS contract", "direct source contract failed", direct.stdout + direct.stderr)
    print("PASS direct source")

    consumer = os.path.join(WORK, "consumer")
    os.makedirs(os.path.join(consumer, ".nift"))
    added = subprocess.run(
        [NIFT, "add", PACKAGE], cwd=consumer, capture_output=True, text=True,
        timeout=20,
    )
    require(added.returncode == 0, "nift add failed", added.stdout + added.stderr)

    with open(os.path.join(consumer, "contract.f"), "w", encoding="utf-8") as output:
        output.write('@import("fuzzy")\n' + contract)
    installed = run("contract.f", consumer)
    require(installed.returncode == 0 and installed.stdout.strip() == "PASS contract", "installed consumer contract failed", installed.stdout + installed.stderr)
    restricted = subprocess.run(
        [NIFT, "contract.f", "--no-process"], cwd=consumer,
        capture_output=True, text=True, timeout=20,
    )
    require(restricted.returncode == 0 and restricted.stdout.strip() == "PASS contract", "no-process contract failed", restricted.stdout + restricted.stderr)
    print("PASS nift add consumer")

    for helper in private_methods:
        with open(os.path.join(consumer, "private.f"), "w", encoding="utf-8") as output:
            output.write(f'@import("fuzzy")\nfuzzy.{helper}()\n')
        result = run("private.f", consumer)
        require(result.returncode != 0 and f"private struct method: {helper}" in result.stderr, f"private helper leaked: {helper}", result.stdout + result.stderr)

    with open(os.path.join(consumer, "global.f"), "w", encoding="utf-8") as output:
        output.write('@import("fuzzy")\nprint(distance)\n')
    global_result = run("global.f", consumer)
    require(global_result.returncode != 0, "unexported global leaked", global_result.stdout + global_result.stderr)
    print("PASS facade privacy")

    for index, expression in enumerate(malformed):
        name = f"malformed-{index}.f"
        with open(os.path.join(consumer, name), "w", encoding="utf-8") as output:
            output.write(f'@import("fuzzy")\n{expression}\n')
        result = run(name, consumer)
        require(result.returncode != 0, f"malformed call succeeded: {expression}", result.stdout + result.stderr)
    print("PASS malformed inputs")
    print("PASS fuzzy test suite")
finally:
    WORK_DIRECTORY.cleanup()
