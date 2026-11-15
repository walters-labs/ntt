//! Dependency-free microbenchmark. Run with `cargo bench --bench transform`.
//! Report medians of seven batches; timings include coefficient-buffer handling.
use std::{hint::black_box, time::Instant};

fn measure(mut f: impl FnMut(), count: u32) -> f64 {
    for _ in 0..20 {
        f();
    }
    let mut times = Vec::new();
    for _ in 0..7 {
        let start = Instant::now();
        for _ in 0..count {
            f();
        }
        times.push(start.elapsed().as_secs_f64() * 1e6 / count as f64);
    }
    times.sort_by(f64::total_cmp);
    times[3]
}

fn main() {
    for (n, q) in [(256, 3329), (1024, 12289), (1024, 12289 * 12289)] {
        let w = ntt::omega(q, n);
        let a: Vec<i64> = (0..n).map(|i| (i as i64 * 7919 + 13) % q).collect();
        let b: Vec<i64> = a.iter().rev().copied().collect();
        let forward = measure(
            || {
                black_box(ntt::ntt(black_box(&a), w, n, q));
            },
            1000,
        );
        let product = measure(
            || {
                black_box(ntt::polymul_ntt(black_box(&a), black_box(&b), n, q, w));
            },
            400,
        );
        let transform = ntt::PreparedNtt::new(n, q, w);
        let mut buffer = vec![0; n];
        let reused_forward = measure(
            || {
                buffer.copy_from_slice(black_box(&a));
                transform.forward_in_place(black_box(&mut buffer));
                black_box(&buffer);
            },
            1000,
        );
        let reused_product = measure(
            || {
                black_box(transform.multiply(black_box(&a), black_box(&b)));
            },
            400,
        );
        println!("n={n} q={q} (microseconds per operation):");
        println!("  one-shot: ntt={forward:.3}, product={product:.3}");
        println!("  reused transform: ntt={reused_forward:.3}, product={reused_product:.3}");
    }
}
