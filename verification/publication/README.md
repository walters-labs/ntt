# Registry-backed release checks

Published on November 17, 2026: **ntt 0.1.10**, **ring-lwe 0.1.9**, and
**module-lwe 0.1.6**. Their published checksums match the exact checked archives.
All release commits and annotated version tags are pushed.

The registry-backed suites passed 70 test executions, NTT Clippy with warnings
denied, and consumer benchmark compilation. NTT's three public transform
graphs match both original proof builds; the two consumer contexts match all
three complete entry graphs. No local prerequisite substitutes were used.

The immutable evidence bundle is `../results/2026-11-17-published.tar.gz`.
Audit its packages, dependency checksums, public tags, source, transcripts,
MIR identities, and manifest with:

```sh
python3 verification/publication/archive.py --check
```

The original NTT proof checkout remains separate from its version-bumped
release worktree so the historical proof gates can still run unchanged.


Publish in dependency order: NTT 0.1.10, Ring-LWE 0.1.9, Module-LWE 0.1.6.
`check.py` never uploads. It requires committed, clean release sources and
checks the exact Cargo package before a separate authorized publishing action.

For each crate it verifies the package's clean Git commit, exact dependency
requirements, packaged Rust bytes, native tests, and pinned-nightly MIR.
NTT's public forward/inverse/multiplication graphs must match the original
1024- and 2048-point proof artifacts. Consumer entries must match the composed
consumer proof. All existing proof gates must pass. The existing fixed-parameter
scope and trusted-checker assumptions remain unchanged.

For consumers, NTT and Ring-LWE dependencies must resolve from crates.io,
with lockfile checksums equal to the previously checked and published package
archives. Local path or Git substitutes are rejected. The exact packages,
MIR, test/build logs, dependency metadata, commits, and index receipts are saved
under `target/verification-publication/`.

Run `python3 verification/publication/check.py ntt` before uploading NTT.
After publication, download its official crates.io index entry and use
`--record-index <index-file>` to require the uploaded checksum to match.
Refresh the next consumer's lockfile from the registry, commit it, and repeat
the check/publish/receipt sequence for Ring-LWE and then Module-LWE.
