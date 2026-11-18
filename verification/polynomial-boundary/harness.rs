use polynomial_ring::Polynomial;

pub fn center_coefficient(a: i64, q: i64) -> i64 {
    let result = ring_lwe::utils::mod_coeffs(Polynomial::new(vec![a]), q);
    result.coeffs().first().copied().unwrap_or(0)
}

// Keep the actual consumer multiplication path, including its private folding
// helper, reachable in the linked MIR. This wrapper is not a verified product.
pub fn multiplication_entry(a: [i64; 4], b: [i64; 4]) -> [i64; 4] {
    let f = Polynomial::new(vec![1, 0, 0, 0, 1]);
    let result = ring_lwe::utils::polymul_fast(
        &Polynomial::new(a.to_vec()), &Polynomial::new(b.to_vec()), 17, &f, 9,
    );
    let mut out = [0; 4];
    out[..result.coeffs().len()].copy_from_slice(result.coeffs());
    out
}
