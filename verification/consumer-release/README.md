# Prepared crate releases

The local release sequence is `ntt 0.1.10`, `ring-lwe 0.1.9`, then
`module-lwe 0.1.6`. The crates.io index was checked before selecting these
versions. The previously published NTT 0.1.9 source differs from the verified
implementation, so retaining that dependency would not carry the proof.

The original NTT checkout remains the proof checkpoint. Its release is prepared
in `/Users/jackson/GitHub/ntt-release`, a separate worktree at the same starting
commit. Ring-LWE and Module-LWE have local clones beside it. Each uses a separate
`codex/verified-release-<version>` branch. Version changes are prepared locally;
publication is a subsequent action.

The consumer manifests require NTT `=0.1.10` and polynomial-ring `=0.5.1`;
Module-LWE requires Ring-LWE `=0.1.9`. The source and packaged manifests use
registry dependencies. Explicit Cargo configuration patches support local
testing before the new prerequisites are published. Other resolved
dependencies and lockfiles are retained in the evidence.

The prepared patches include the verified roots, fixed transform lengths,
independent CLI overrides, in-place folding/centering, and the padding helper.
Persistent consumer integration tests cover the three fixed multiplication
tuples against an independent schoolbook formula, malformed inputs, default
parameters, and zero/trimmed module-vector inputs. NTT's implementation bytes
are unchanged from the proved checkpoint; only its release metadata and
documentation change.

`run.py` creates and verifies the three `.crate` archives in dependency order.
Cargo's package verifier uses explicit patches for the exact local prerequisite checkouts while
the new versions remain unpublished. The stronger tests and MIR build then
use the extracted `.crate` sources, with local patches for the two unpublished
prerequisites. These are explicitly recorded local substitutions, rather than
a claim that the versions already exist in the public registry.

All three extracted packages run their test suites and documentation examples.
NTT is also tested in release mode and checked with Clippy warnings denied;
both consumer benchmark sets must compile. A pinned-nightly MIR build of the
actual packaged Ring-LWE dependency uses the unchanged fixed-array harness.
Its complete reachable graphs at all three tuples must match the successful
consumer-call checkpoint, modulo bijective identifier renaming and source
positions. Path remapping aligns panic-location strings as well. The existing
consumer-call acceptance gate must pass before accepting that transfer.
This carries the existing proof scope and trusted-checker assumptions; it does
not broaden the claim to other parameter tuples or cryptosystems.

The source plan is checked before any checkout is changed. `apply.py` verifies
the expected Git bases, clean consumer checkouts, prepared file hashes, and the
successful package/proof report, then creates the release branches and NTT
worktree. It preserves the original proof checkout. The final package pass
reads from these actual release repositories, so its archive hashes also bind
their real Git metadata.

From the original NTT repository, audit the final package checkpoint with:

```sh
python3 verification/consumer-release/run.py --from-checkouts --check
python3 verification/consumer-release/apply.py --check
```

The reports and package archives are under
`target/verification-consumer-release/final/`. `application-plan.json` and
`application-report.json` one level above bind the applied source. A separate
archive in `verification/results/` retains the source, exact packages, lockfiles,
MIR, transcripts, and file hashes. Earlier proof archives supply the underlying
convolution, transform, constructor, padding, folding, and composition proofs.

For publication, first review/commit the three branches. Publish NTT 0.1.10,
then verify and publish Ring-LWE 0.1.9, then verify and publish Module-LWE 0.1.6.
After each prerequisite is available, repeat registry-backed package
verification without the local registry patches and archive the resulting
final package hashes. New registry checksums may change packaged lockfiles;
the release verifier must be repeated against those final artifacts before
making a claim about the published packages. No publishing command is run by
these scripts.
