# fuzzy

Deterministic fuzzy string matching for Nift with no dependencies or runtime
resources.

## Install

```text
nift add /path/to/fuzzy
```

```nift
@import("fuzzy")

print(fuzzy.distance("kitten", "sitting"))
print(fuzzy.matches("book", "back", 2))
print(fuzzy.filter("cat", ["cat", "cut", "dog"], 1))
print(fuzzy.rank("cat", ["bat", "cat", "cut"]))
```

Only the `fuzzy` facade is exported. It provides:

- `fuzzy.distance(a, b)` returns the Levenshtein edit distance.
- `fuzzy.matches(query, candidate, max_distance?)` returns whether the distance
  is at most `max_distance`. The default is `2`.
- `fuzzy.filter(query, candidates, max_distance?)` returns matching candidate
  strings in their original order. The default is `2`.
- `fuzzy.rank(query, candidates)` returns every candidate as an object with
  `candidate` and `distance` fields, ordered by ascending distance. Equal
  distances retain the candidates' original order.

## Semantics

Inputs are explicitly encoded as UTF-8 bytes and compared case-insensitively
using ASCII folding: integer bytes `65` through `90` (`A` to `Z`) are mapped to
`97` through `122` (`a` to `z`). All other bytes are unchanged. Distance is
computed over bytes, not Unicode code points or grapheme clusters. Nift source
strings are UTF-8, so a non-ASCII character can contribute more than one edit.
For example, `distance("é", "e")` is `2`, `distance("Ä", "ä")` is `1`, and
`distance("😀", "")` is `4`.

The algorithm uses two dynamic-programming rows and deterministic insertion
ranking. Duplicate candidates are retained. Empty strings and empty candidate
arrays are valid.

`a`, `b`, `query`, and every candidate must be strings. `candidates` must be an
array. `max_distance` must be a non-negative integer, and at most one optional
argument is accepted. Invalid calls fail with a Nift runtime error; values are
never coerced.

## Test

```text
python3 tests/test.py /path/to/nift /path/to/fuzzy
```

The suite tests direct source import, installation with `nift add`, facade and
helper privacy, malformed calls, empty and Unicode boundaries, stable ranking,
and repeat determinism. It is offline and removes its temporary work tree.
