# Verification checkpoints

## November 17: 2048-point proofs

Both concrete specifications and six fixed-size Rust wrappers are implemented.
The current MIR build is retained under SHA-256
`a4c42718c1d5c926b65d3e5ca936aec4127a1f6ac1396ddcc9163f4e0007dd3a`.
Production Rust is unchanged; the harness additions call the existing public APIs.
**Both 2048-point forward, inverse, and cyclic-multiplication proofs are complete
for every signed `i64` input.** Each Rust run passed all 33 MIR contracts with
vacuity checking: four arithmetic, two butterfly, 22 stage, two kernel, and
three public-operation contracts.

| Tuple `(N,q,root)` | Rust wall seconds | Monotonic seconds | Child CPU seconds | Maximum child RSS |
| --- | ---: | ---: | ---: | ---: |
| `(2048,12289,1945)` | 8,687.053 | 8,686.523 | 8,007.723 | 4.45 GiB (4,773,167,104 bytes) |
| `(2048,151019521,51689479)` | 9,259.766 | 9,259.158 | 8,561.967 | 6.44 GiB (6,911,344,640 bytes) |

The final gates are `paired-2048-12289-20261117T055025426841Z.json` and
`paired-2048-151019521-20261117T060232215654Z.json`. Each connects a complete
mathematical graph, complete transform-model graph, actual parameter-instance
imports, current Rust sources, and the exact MIR build. The squared-modulus
mathematical graph includes its complete 1024-point dependency graph and the
fresh SAW checks matching that graph's exported theorem to the required premise.

All reports, transcripts, core exports, source versions, exact MIR, toolchain
records, and negative controls are retained in `2026-11-17.tar.gz`, with per-file
SHA-256 hashes in `manifest.json`. The required November 16 archive is retained
inside it for the checked historical half-size theorem. Current sources are
under `source/2026-11-17/`; run artifacts retain repository-relative paths.
This is an audit/replay archive, not an imported SAW proof certificate.

The mathematical/model controllers cache every checked node and block. Rust
jobs took about 2 h 25 min / 2 h 34 min; clean mathematical and model replays add
substantial time. Allow several hours per tuple on this 16 GiB Mac. Rechecking
the completed graphs and gates takes under a second here. Parallel jobs' wall
times and memory peaks must not be added as a single elapsed time or aggregate
memory measurement. The `metrics-2048-*.json` files summarize the exact unique
successful runs referenced by each graph, including reused dependencies.

The following records document the proof strategy and earlier attempts.

The 2048-point schoolbook recurrence at modulus 12289 passed with a 10 GiB heap:
1,591.212 wall seconds, 1,591.180 monotonic seconds, 1,559.781 child CPU seconds,
and 6.42 GiB maximum child RSS (6,890,979,328 bytes). The first probe hit its
ten-minute internal deadline after 608.234 wall seconds, with 5.72 GiB maximum
child RSS. The successful retry allowed thirty minutes internally and 1,900
seconds externally; it did not waive a proof obligation.

The top-level spectral-product sum and difference identities passed independently
at both moduli. At 12289 they used 24.300 and 23.877 seconds with 0.46/0.47 GiB
maximum child RSS. At 151019521 they used 26.264 and 25.575 seconds with 0.48/0.49
GiB. These runs had 2 GiB heap caps. The first combined Rust/model attempt proved
all 22 stage contracts but exhausted its 10 GiB heap in the forward DFT model.
That unsuccessful run took 6,174.601 seconds and reached 9.16 GiB maximum child
RSS; it does not establish a complete transform proof. Rust and the pure models
are now checked in separate processes. The large Rust runs use 12 GiB heaps,
32 MiB nurseries, vacuity checking, and five-hour external failure limits.

The independent forward model at modulus 12289 passed in 939.400 wall seconds
with 5.54 GiB maximum child RSS. Its inverse model passed as 32 independently
proved 64-output blocks; the largest block used 1.342 GiB. The complete-coverage
implication took 13.609 seconds and 0.26 GiB. The checked product bridge also
passed. Every block quantifies all signed input coefficients.

A separate unpartitioned inverse-decomposition attempt exhausted a 6 GiB heap
after 1,601.346 seconds, at 6.17 GiB maximum child RSS. The mathematical forward
decomposition, inverse decomposition, and convolution recurrence now support the
same closed-block and coverage workflow. All 32 replacement inverse blocks at
12289 passed around 1 GiB each. Coverage used 16.750 seconds / 0.26 GiB;
conditional composition used 4.905 seconds / 0.22 GiB; the final spectral bridge
used 13.259 seconds / 0.33 GiB. The complete first mathematical graph passed.
Existing successful nodes remain cached.

Both transform-model graphs are complete. At modulus 151019521, all 32 forward
and 32 inverse blocks passed; maximum child RSS was 0.868 / 1.382 GiB. Their
checked product bridge also passed. The final gates require these models,
the Rust proofs, and the mathematical convolution proofs together.

The original squared-modulus half-size attempt reached length 1024, then hit
the ten-minute forward-decomposition limit. It used 1,661.131 wall seconds and
3.24 GiB maximum child RSS with a 10 GiB heap; this was a deadline failure.
The replacement proves the internal `(1024,151019521,61307834)` mathematical
instance as its own component graph, with closed output blocks at that level.
A separate adapter checks the exported direct convolution proposition against
the precise half-size premise of the 2048-point graph. The controller requires
the complete successful nested graph; an incomplete/failed graph was rejected
by a negative control.

The full three-layer block workflow passed at 8 points, including the binary
recurrence and both explicit composition bridges. Additional negative controls
reject missing blocks, duplicate offsets, a wrong proof family/component,
changed exports, and unmatched coverage premises. An interruption control
confirmed that both parallel proof workers and their solver children stop.

One concurrent run exposed a report filename collision: two processes received
the same microsecond timestamp. The hash checker rejected the overwritten
report. The runner now reserves transcript filenames atomically; a synthetic
test with an intentionally frozen clock confirmed distinct intact logs and
reports. Only the affected block needs to be proved again.

The mathematical workflow now proves its half-size theorem and seven component
identities in separate processes. It proves explicit conditional composition and
spectral-bridge theorems, checks serialized propositions with `check_convertible`,
and requires successful proofs of every premise. Exported propositions are kept
by hash. This is a checked logical dependency graph; core files and logs are not
imported as SAW proof objects. The recurrence adapter also checks that its
predicate is textually identical to the original proved expression, then checks
definitional equality with the shared component predicate.

The full 8-point graph passed, as did its connection to a fresh Rust proof and
the exact MIR build. Negative controls rejected a missing premise, failed leaf,
wrong component selector, changed shared specification, changed proposition
export, and mismatched composition input. Repeating the controller reuses checked
nodes. The original 8-point mathematical theorem/bridge also passed after the
structural bridge rules were extracted to `bridge-lemmas.saw`.

The fixed-modulus scalar and butterfly contracts now return their exact formulas
without redundant range postconditions. Callers derive the same required bounds
from proved `normalize_range` and `repr_range` rules. This removes accumulated
scalar hypotheses; the whole-kernel canonical-output contracts remain. The first
small trial exposed a missing range rewrite in the proof tactic; after adding it,
the staged 8-point check and all 48 default MIR contracts passed. The 256-point
full regression used 375.700 seconds and 2.76 GiB maximum child RSS while the
large recurrence was also running. The three direct small cases passed in
78.004, 214.981, and 79.671 seconds under 2 GiB heaps.

## November 16: split-proof workflow and sleep diagnosis

**The complete 1024-point forward, inverse, and cyclic-multiplication proofs passed.**
The mathematical run used a 10 GiB heap, a 1,800-second external deadline, and
temporary idle-sleep prevention. Wall time was 1,473.838 seconds, monotonic elapsed
time was 1,473.860 seconds, child CPU time was 1,458.831 seconds, and maximum child
RSS was 6.53 GiB (7,008,534,528 bytes). All recursive dependencies were proved in
that process.

The Rust run passed all 31 MIR contracts with vacuity checking: four arithmetic,
two butterfly, twenty stage, two kernel, and three public-operation contracts.
The direct-DFT model proofs also passed. It used a 10 GiB heap and a 3,600-second
external deadline, with temporary idle-sleep prevention. Wall time was
2,095.494 seconds, monotonic elapsed time was 2,095.469 seconds, child CPU time
was 2,067.397 seconds, and maximum child RSS was 5.99 GiB (6,433,193,984 bytes).
The two successful runs were sequential, totaling about 59.5 minutes; their
memory peaks are separate. These RSS figures do not measure aggregate memory
across all processes or equal the historical physical-footprint measurement.

The final provenance check passed and recorded the connection in
`paired-1024-12289-20261116T235742904639Z.json`. The corresponding run stems are
`convolution-1024-20261116T224934434035Z` and
`spectral-1024-12289-20261116T232238150010Z`. Their reports, transcripts, exact
MIR artifact, proof-source snapshot, and toolchain manifest are retained in
`2026-11-16.tar.gz`, with per-file SHA-256 hashes in its `manifest.json`.
Sources are under `source/2026-11-16/`; the MIR and run records retain their
repository-relative paths. The archive is an audit record, not an imported
SAW proof certificate; reruns still require the pinned verification toolchain.
At that November 16 checkpoint, neither 2048-point case had been attempted.

The shared `multiplication-spec.saw` defines the spectral product used by both
the mathematical proof and the new Rust contract. The former proves its equality
to cyclic convolution for every pair of coefficient arrays; the latter proves
that Rust returns it for normalized arbitrary signed inputs. This separates
proof histories without assuming a missing mathematical theorem in the Rust run.
`check-split.py` checks successful reports, matching actual proof dependencies,
the shared definition, current Rust inputs, and the exact MIR build provenance.

The complete split workflow passed at `(8,17,9)`: the mathematical proof and
bridge used 12.034 seconds and 0.22 GiB maximum child RSS; the Rust run used
22.299 seconds and 1.36 GiB. Both used a 6 GiB heap. The Rust run enabled
vacuity checking. Negative provenance tests rejected a failed run, a changed
entry, a changed shared definition, and a changed MIR artifact. The build helper
retains MIR artifacts by SHA-256 so subsequent builds cannot overwrite evidence.

An earlier 10 GiB combined-math attempt timed out in the 512-point inverse
decomposition. SAW reported 161.895 CPU seconds versus 2,352.213 elapsed seconds;
the runner's monotonic clock recorded 189.787 seconds and maximum child RSS was
2.96 GiB. The macOS power log confirmed repeated sleep/dark-wake cycles during
that run. This was not a heap-limit failure. Older wall-time and garbage-collection
elapsed figures can include sleep and should not be equated with CPU effort.

The runner now optionally uses `caffeinate -i -w` on macOS, enforces its external
deadline against wall time, and records wall, monotonic, and child CPU times.
The temporary sleep assertion and its release were checked. Synthetic controls
also checked deadline enforcement, child-process cleanup, and failing exit status.

Inspection of the installed SAW 1.6 source found that its theorem database retains
theorems and their proof evidence, including intermediate sequents and rewrite
rules. This explains why independent checks do not establish the memory needed
to retain and compose them in one process. A 64-output recurrence probe already
had a final goal of only three DAG nodes; another final evaluation left it at
three, so final solver-goal simplification was not promoted. The expensive work
is in expanding and rewriting the dense specifications and retaining the evidence.
See [SAW's theorem and evidence representation](https://github.com/GaloisInc/saw-script/blob/68eed5f/saw-central/src/SAWCentral/Proof.hs#L942).

An initial Rust run with a 1,800-second overall deadline was deliberately
stopped after consulting the earlier stage/model/kernel timings: that deadline
was too short for the expected work. Its report records exit code -15. The
successful replacement above used a 3,600-second deadline; no proof obligation
was waived. The split regression and unsuccessful diagnostic runs are archived
alongside the successful pair and the historical results below. No proof process
was left running after the completed pair.

## November 16: bounded mathematical checks passed

`recurrence-1024.saw` proved the even/odd schoolbook-convolution recurrence for
two arbitrary 1024-element coefficient arrays at modulus 12289. It uses the
same algebraic tactics as the full theorem, extracted without changes into
`math-tactics.saw`, and checks all outputs in chunks of 64. No Rust MIR was loaded.

`forward-split-1024.saw` subsequently proved that the direct 1024-point DFT
equals the combination of its even/odd 512-point DFTs, for arbitrary coefficient
arrays. The roots come from the same validated parameters used by the full
convolution proof, and this check also uses 64-output chunks.

`inverse-split-1024.saw` proved the corresponding inverse decomposition,
including the inverse-length scaling and the half-sum/half-difference inputs.
It uses the same validated parameters and 64-output chunking.

`inverse-linearity-1024.saw` proved inverse additivity modulo 12289 for arbitrary
512-element arrays, using the half-size root and inverse length required by the
1024-point convolution theorem.

`inverse-shift-1024.saw` proved that multiplying an arbitrary 512-element input
by successive powers of the half-size forward root before the inverse transform
equals rotating the inverse-transform output right by one position. It uses
the same half-size parameters and 64-output chunking.

`spectral-sums-1024.saw` proved the sum decomposition of the pointwise product
of two combined spectra, for four arbitrary 512-element coefficient arrays.
Taking the modular half-sums cancels the cross terms and leaves the first
pair's pointwise product plus the second pair's product multiplied by successive
powers of the half-size root. It uses the same parameters and 64-output chunking.

`spectral-diffs-1024.saw` proved the corresponding difference decomposition
for four arbitrary 512-element coefficient arrays. Subtracting the two product
halves, dividing by two modulo 12289, and removing the forward-root powers
leaves the sum of the cross products. It uses the same parameters and
64-output chunking.

| Isolated lemma | Result | Elapsed time | Maximum child RSS |
| --- | --- | --- | --- |
| Schoolbook recurrence | Passed, exit 0 | 238.789 seconds | 4.28 GiB |
| Forward DFT decomposition | Passed, exit 0 | 248.036 seconds | 2.28 GiB |
| Inverse DFT decomposition | Passed, exit 0 | 246.318 seconds | 3.68 GiB |
| Inverse linearity (512-point subtransforms) | Passed, exit 0 | 100.791 seconds | 2.45 GiB |
| Inverse shift (512-point subtransforms) | Passed, exit 0 | 64.971 seconds | 1.63 GiB |
| Spectral product sums (512 outputs) | Passed, exit 0 | 9.629 seconds | 0.33 GiB |
| Spectral product differences (512 outputs) | Passed, exit 0 | 10.489 seconds | 0.34 GiB |

- All seven runs used a **6 GiB SAW heap** and a **600-second external wall deadline**.
- The small complete 16-point mathematical theorem and bridge passed after the
  shared-tactic extraction, in 14.499 seconds with 0.22 GiB maximum child RSS.
- The external timeout was checked with a synthetic parent/solver-child pair;
  both were stopped at the deadline. Termination cleanup is also checked.

The logs and source-hash reports are retained in `2026-11-16.tar.gz`. These
memory measurements are resident-memory statistics, not the physical-footprint
measurement used for the previous 29 GiB session. The heap limit also does not
bound aggregate memory of all solver processes.

This earlier checkpoint established all seven top-level component identities
independently within the stated budget. Those checks alone did **not** establish
the full 1024-point convolution theorem or public multiplication API; the later
successful pair is recorded above. Separate logs cannot be imported as proved
SAW theorems.

### Combined convolution attempt: heap limit reached

`convolution-1024.saw` runs the recursive theorem and specification bridge in one
fresh process, proving every smaller-length dependency before reuse. The first
attempt used a 6 GiB SAW heap and a 1,800-second external deadline. It failed
with exit code 2 and `heap overflow` during the 1024-point schoolbook recurrence.
Maximum child RSS was 6.12 GiB. The runner recorded 1,582.493 seconds of monotonic
elapsed time; SAW's runtime report recorded 1,797.386 elapsed seconds. These
measurements differ and are retained as reported, without equating them.

The complete convolution theorem passed through length 512. At length 1024,
forward decomposition, inverse decomposition, inverse linearity, and inverse
shift passed before the heap failure. The final 1024-point composition and
specification bridge were not reached. This is a resource failure, not a
counterexample, and it does not establish the full multiplication claim.

SAW reported 972.949 elapsed seconds in garbage collection, over half its
reported elapsed run time. The 64-output recurrence that passed independently
did not fit the same heap cap after the other proofs in the combined session.
The failed log and source-hash report are retained in `2026-11-16.tar.gz`.

An isolated recurrence experiment with 32-output chunks passed in 238.592 seconds
with 4.34 GiB maximum child RSS. The original 64-output check used 238.789 seconds
and 4.28 GiB. Halving the chunks did not improve peak memory, so the 64-output
entry was restored. The experimental entry, log, and hash report are archived.

A second isolated experiment wrapped each recursive vector half in `subproof`,
retaining the original 64-output chunks. It passed in 242.608 seconds with
4.55 GiB maximum child RSS, also offering no memory improvement. The variant
and its entry, log, and hash report are archived; `vector-proofs.saw` is unchanged.
Neither experiment justifies another full run with the same heap budget.
At that checkpoint, the next diagnostic was to examine retained proof data
between lemmas before changing the composition strategy. No proof process was
left running at that checkpoint.

## November 15: cleanup and checkpoint

Work was paused at this checkpoint; no proof process was left running overnight.

### Established results

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
  under this limit. At that checkpoint, neither 2048-point case had been attempted.

### Resume instructions at that checkpoint

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

### Retained evidence

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
