# Paused polynomial-boundary work

This is the historical pause snapshot. Work has resumed; see
[the maintained checkpoint](README.md) for the actual-consumer proof suite.
The statements below describe only the earlier pause.

Paused at the user's request. No proof processes remain running. No production
source was changed during this step, and nothing was committed.

Successful exploratory checks:

- `constructor-512-bulk.saw`: the actual `Polynomial<i64>::new` constructor
  preserves its backing coefficients and capacity, returns length at most 512,
  discards only trailing zeros, and retains a nonzero last coefficient when
  nonempty. All signed inputs and valid capacities >= 512 are covered.
  Passed in 48.464 seconds with about 0.36 GiB maximum child RSS.
- `padding-8.saw`: fixed-allocation prototype padding with arbitrary logical
  input length 0..8 and backing storage/capacity >= 8. Passed in 1.242 seconds.
  This is a prototype, not an integrated or full-size consumer-padding proof.

The saved probe scripts use `get_opt 1` for their MIR artifact. The exact MIR,
reports, transcripts, Cargo files, and scripts are retained in
`../results/2026-11-17-boundary-paused.tar.gz`.

Resume from `target/verification-polynomial-boundary/`. The corresponding
constructor proof for 1024 coefficients has not passed. A bulk version is
prepared as `constructor-1024-bulk.saw`; grouped-postcondition versions are
also prepared, but have not run. The original per-coefficient postcondition
approach timed out because it repeated expensive term translation for hundreds
of separate goals. Combining the assertions allowed the 512 case to pass.

Useful details: the installed SAW 1.6 `mir_find_adt` and `mir_find_name` return
pure values (use `let`). Generic constructor lookup requires `mir_find_name`.
The constructor setup explicitly builds the Vec representation to retain the
original typed raw-pointer handle for frame assertions; `mir_points_to_multi`
rejects handles containing casts. The layout follows the installed SAW Vec
setup helper and pinned mir-json standard library.

Next: finish the 1024 constructor contract; reuse the checked constructor
summary to simplify coefficient-view checks; scale prototype padding to the two
consumer degrees, accounting for empty vectors and smaller actual capacities;
then integrate any necessary padding change with source binding and native
regressions. Full adapter composition remains open.
