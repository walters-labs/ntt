use polynomial_ring::Polynomial;

fn coefficient<const D: usize>(a: [i64; D], index: usize) -> i64 {
    let polynomial = Polynomial::new(a.to_vec());
    polynomial.coeffs().get(index).copied().unwrap_or(0)
}

pub fn coefficient_512(a: [i64; 512], index: usize) -> i64 { coefficient(a, index) }
pub fn coefficient_1024(a: [i64; 1024], index: usize) -> i64 { coefficient(a, index) }

fn length<const D: usize>(a: [i64; D]) -> usize {
    Polynomial::new(a.to_vec()).coeffs().len()
}
pub fn length_512(a: [i64; 512]) -> usize { length(a) }
pub fn length_1024(a: [i64; 1024]) -> usize { length(a) }

pub fn padded(polynomial: &Polynomial<i64>, n: usize) -> Vec<i64> {
    assert!(polynomial.coeffs().len() <= n);
    let mut output = vec![0; n];
    output[..polynomial.coeffs().len()].copy_from_slice(polynomial.coeffs());
    output
}
