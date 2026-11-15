# Verification checkpoint — November 15, 2026

Work is paused. No proof process is being left running overnight.

## Established results

- Forward, inverse, and cyclic multiplication at `(8,17,9)`, `(16,17,3)`,
  `(8,289,110)`, and `(256,12289,8340)`: 48 required MIR contracts in total.
- Arithmetic, butterfly, parameter, and ML-KEM power foundations: 139 contracts.
- At `(1024,12289,10302)`: arithmetic, butterflies, all 20 stages, direct-DFT
  models, both kernels, and public forward/inverse operations passed.
  Public cyclic multiplication is **not proved**. The interactive transcript
  includes retries and failures; its raw success count includes a repeated
  forward-kernel proof and is not a count of distinct completed contracts.
- The 1024-point schoolbook recurrence passed alone with 64-output chunks in
  about 344 seconds. Completing the entire convolution theorem in the large
  session timed out, with a peak process footprint of about 29 GiB.
- The 6 GiB heap setting passed the small mathematical regression and all seven
  contracts of the 8-point Rust/MIR case. No complete 1024-point run has passed
  under this limit. Neither 2048-point case has been attempted.

## Resume here

The target remains the three fixed tuples in [the roadmap](../roadmap.md), with
arbitrary signed coefficients. Consumer adapters and arbitrary generic API
parameters are separate work.

Start with a **math-only, isolated recurrence check** in a fresh SAW process,
with a short explicit timeout and `+RTS -M6G -RTS`. Establish its memory use
before attempting another full run. Do not restart the full 1024-point script
as the first experiment.

Keep expensive lemmas in separate top-level proof commands. A failed SAW
`include` rolls back that include's bindings, even when earlier statements
succeeded; retrying the whole include repeats that work. Native `define` aliases
can survive such a failure and collide on redefinition.

An experimental `subproof` wrapper around each half of the vector-splitting
tactic passed the 16-point mathematical check. Its 1024-point retry was stopped
while closing the session; treat it as inconclusive. It has not been promoted
into the maintained scripts. The archive retains this small experiment for
reference, along with the isolated recurrence that definitely passed.

## Retained evidence

`2026-11-15.tar.gz` contains selected original transcripts, the relevant small
experiment scripts, the dependency lockfile, and hashes of the source used for
the 1024-point MIR build. `manifest.json` inside the archive lists file hashes.
The archived paths are relative to the repository root. Historical scripts may
refer to deleted build directories; this archive is an audit record, not a
standalone runner or reusable proof certificate.

The original MIR loaded by the interactive session had SHA-256
`8e474cb30f6d81aae08060c93204d2a1e8c29d2929db4fd7fe875c41e057429c`.
It was later overwritten by a rebuild with different allocation identifiers;
the production Rust, harness, and mathematical specification were unchanged.
The archive does not contain that original MIR artifact.

Disposable build directories, abandoned Verus tooling, and duplicate diagnostic
experiments have been removed. The pinned Cryptol, SAW, mir-json installation,
translated standard libraries, and required Rust nightly are retained. The
normal runners rebuild the project's MIR and logs when needed.

Before this checkpoint, formatting, Clippy with warnings denied, and all 21
Rust tests (including doctests) passed in debug and release modes. A fresh MIR
build also passed after deleting mir-json's installation build cache. No large
formal proof was rerun during cleanup.
