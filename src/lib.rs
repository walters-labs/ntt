//! Radix-2 transforms and cyclic polynomial multiplication over modular rings.
//!
//! Use [`PreparedNtt`] to reuse twiddle factors and transform buffers in place.
//! The free functions retain the allocating interface for occasional transforms.

use reikna::factor::quick_factorize;
use std::collections::HashMap;

mod prepared;
pub use prepared::PreparedNtt;

#[cfg(test)]
mod test;

#[cfg(any(test, crux))]
#[path = "../verification/harness.rs"]
mod verification;

fn mod_normalize(a: i64, p: i64) -> i64 {
    a.rem_euclid(p)
}

// All arithmetic helpers take canonical residues: 0 <= a, b < p.
fn mod_add(a: i64, b: i64, p: i64) -> i64 {
    if a >= p - b {
        a - (p - b)
    } else {
        a + b
    }
}

fn mod_sub(a: i64, b: i64, p: i64) -> i64 {
    if a >= b {
        a - b
    } else {
        p - (b - a)
    }
}

fn mod_mul(a: i64, b: i64, p: i64) -> i64 {
    // (p - 1)^2 fits in i64 below this bound. Larger moduli need widening.
    if p <= 3_037_000_500 {
        (a * b) % p
    } else {
        ((a as i128 * b as i128) % p as i128) as i64
    }
}

/// Modular exponentiation
/// # Arguments
///
/// * `base` - Base of the exponentiation.
/// * `exp` - Exponent.
/// * `p` - Modulus, greater than one.
///
/// # Returns
/// The result of the exponentiation modulo `p`.
///
/// # Panics
/// Panics if `p <= 1` or `exp < 0`.
pub fn mod_exp(mut base: i64, mut exp: i64, p: i64) -> i64 {
    assert!(p > 1, "modulus must be greater than one");
    assert!(exp >= 0, "exponent must be nonnegative");
    let mut result = 1;
    base = base.rem_euclid(p);
    while exp > 0 {
        if exp % 2 == 1 {
            result = mod_mul(result, base, p);
        }
        base = mod_mul(base, base, p);
        exp /= 2;
    }
    result
}

/// Extended Euclidean algorithm
/// # Arguments
///
/// * `a` - First number.
/// * `b` - Second number.
///
/// # Returns
/// A tuple with the greatest common divisor and the Bézout coefficients.
fn extended_gcd(a: i128, b: i128) -> (i128, i128, i128) {
    if b == 0 {
        (a, 1, 0) // gcd, x, y
    } else {
        let (gcd, x1, y1) = extended_gcd(b, a % b);
        (gcd, y1, x1 - (a / b) * y1)
    }
}

/// Compute the modular inverse of a modulo modulus
fn mod_inv(a: i64, modulus: i64) -> i64 {
    let (gcd, x, _) = extended_gcd(a.rem_euclid(modulus) as i128, modulus as i128);
    if gcd != 1 {
        panic!("{} and {} are not coprime, no inverse exists", a, modulus);
    }
    x.rem_euclid(modulus as i128) as i64
}

/// Compute n-th root of unity (omega) for p not necessarily prime
/// # Arguments
///
/// * `modulus` - Odd modulus greater than one. `n` must divide the totient of
///   each prime-power factor.
/// * `n` - Order of the root of unity.
///
/// # Returns
/// The n-th root of unity modulo `modulus`.
/// For a radix-2 transform, choose `n` to be a power of two.
///
/// # Panics
/// Panics for invalid moduli or orders, or if the required roots do not exist.
///
/// # Examples
///
/// ```
/// // For modulus = 17^2 = 289, we compute and verify an 8th root of unity.
/// let modulus = 17 * 17;
/// let n = 8;
/// let omega = ntt::omega(modulus, n);
/// assert!(ntt::verify_root_of_unity(omega,n.try_into().unwrap(),modulus));
///
/// // For modulus = 17*41*73, we compute and verify an 8th root of unity.
/// let modulus = 17*41*73;
/// let omega = ntt::omega(modulus, n);
/// assert!(ntt::verify_root_of_unity(omega,n.try_into().unwrap(),modulus));
/// ```
pub fn omega(modulus: i64, n: usize) -> i64 {
    assert!(
        modulus > 1 && modulus % 2 == 1,
        "modulus must be odd and greater than one"
    );
    let order = i64::try_from(n).expect("root order must fit in i64");
    assert!(order > 0, "root order must be positive");
    if n == 1 {
        return 1;
    }
    let factors = factorize(modulus);
    if factors.len() == 1 {
        let (p, e) = factors.into_iter().next().unwrap();
        let root = primitive_root(p, e); // primitive root mod p
        let grp_size = (modulus / p) * (p - 1);
        assert!(grp_size % order == 0, "{} does not divide {}", n, grp_size);
        mod_exp(root, grp_size / order, modulus)
    } else {
        root_of_unity(modulus, order)
    }
}

/// Forward transform using NTT, output bit-reversed
/// # Arguments
///
/// * `a` - Input coefficients, normalized modulo `p` before transformation.
/// * `omega` - Principal root of unity modulo `p`.
/// * `n` - Length of the input vector and the result.
/// * `p` - Coefficient modulus; see [`PreparedNtt::new`].
///
/// # Returns
/// A vector representing the NTT of the input vector.
///
/// # Examples
///
/// ```
/// let modulus: i64 = 17; // modulus, n must divide phi(p^k) for each prime factor p
/// let n: usize = 8;  // Length of the NTT (must be a power of 2)
/// let omega = ntt::omega(modulus, n); // n-th root of unity
/// let mut a = vec![1, 2, 3, 4];
/// a.resize(n, 0);
/// // Perform the forward NTT
/// let a_ntt = ntt::ntt(&a, omega, n, modulus);
/// let a_ntt_expected = vec![10, 15, 6, 7, 16, 13, 11, 15];
/// assert_eq!(a_ntt, a_ntt_expected);
/// ```
///
/// # Panics
/// Panics if `a.len() != n` or the parameters violate [`PreparedNtt::new`]'s contract.
/// Coefficients may be any `i64`; outputs are canonical residues.
pub fn ntt(a: &[i64], omega: i64, n: usize, p: i64) -> Vec<i64> {
    assert_eq!(a.len(), n, "input length must equal the transform length");
    let transform = PreparedNtt::new(n, p, omega);
    let mut result = a.to_vec();
    transform.forward_in_place(&mut result);
    result
}

/// Inverse transform using INTT, input bit-reversed
/// # Arguments
///
/// * `a` - Input vector (bit-reversed).
/// * `omega` - Principal root of unity modulo `p`.
/// * `n` - Length of the input vector and the result.
/// * `p` - Coefficient modulus; see [`PreparedNtt::new`].
///
/// # Returns
/// A vector representing the inverse NTT of the input vector.
///
/// # Panics
/// Panics if `a.len() != n` or the parameters violate [`PreparedNtt::new`]'s contract.
pub fn intt(a: &[i64], omega: i64, n: usize, p: i64) -> Vec<i64> {
    assert_eq!(a.len(), n, "input length must equal the transform length");
    let transform = PreparedNtt::new(n, p, omega);
    let mut result = a.to_vec();
    transform.inverse_in_place(&mut result);
    result
}

/// Naive polynomial multiplication
/// # Arguments
///
/// * `a` - First polynomial (as a vector of coefficients).
/// * `b` - Second polynomial (as a vector of coefficients).
/// * `n` - Length of the polynomials and the result.
/// * `p` - Coefficient modulus, greater than one.
///
/// # Returns
/// The cyclic polynomial product modulo `x^n - 1` and `p`.
/// Inputs may have any length and any `i64` coefficients.
///
/// # Panics
/// Panics if `n <= 0`, `n` does not fit in `usize`, or `p <= 1`.
pub fn polymul(a: &[i64], b: &[i64], n: i64, p: i64) -> Vec<i64> {
    assert!(n > 0, "polynomial length must be positive");
    assert!(p > 1, "modulus must be greater than one");
    let n = usize::try_from(n).expect("polynomial length must fit in usize");
    let mut result = vec![0; n];
    for (i, &a_i) in a.iter().enumerate() {
        for (j, &b_j) in b.iter().enumerate() {
            let k = ((i % n) + (j % n)) % n;
            result[k] = mod_add(
                result[k],
                mod_mul(a_i.rem_euclid(p), b_j.rem_euclid(p), p),
                p,
            );
        }
    }
    result
}

/// Multiply two polynomials using NTT (Number Theoretic Transform)
///
/// # Arguments
///
/// * `a` - First polynomial (as a vector of coefficients).
/// * `b` - Second polynomial (as a vector of coefficients).
/// * `n` - Length of the polynomials and the NTT (must be a power of 2).
/// * `p` - Coefficient modulus; see [`PreparedNtt::new`].
/// * `omega` - Principal root of unity modulo `p`.
///
/// # Returns
/// The cyclic polynomial product modulo `x^n - 1` and `p`.
///
/// # Panics
/// Panics if either input has length other than `n`, or the parameters violate
/// [`PreparedNtt::new`]'s contract.
pub fn polymul_ntt(a: &[i64], b: &[i64], n: usize, p: i64, omega: i64) -> Vec<i64> {
    assert_eq!(a.len(), n, "input length must equal the transform length");
    assert_eq!(b.len(), n, "input length must equal the transform length");
    PreparedNtt::new(n, p, omega).multiply(a, b)
}

/// Compute the prime factorization of `n` (with multiplicities)
/// Uses reikna::quick_factorize internally
/// # Arguments
///
/// * `n` - Number to factorize.
///
/// # Returns
/// A HashMap with the prime factors of `n` as keys and their multiplicities as values.
fn factorize(n: i64) -> HashMap<i64, u32> {
    let mut factors = HashMap::new();
    for factor in quick_factorize(n as u64) {
        *factors.entry(factor as i64).or_insert(0) += 1;
    }
    factors
}

/// Compute a primitive root modulo `p^e`, for prime `p`.
/// Tests the lift modulo `p^2`; for odd primes, that lift generates modulo `p^e`.
/// # Arguments
///
/// * `p` - Prime modulus.
/// * `e` - Exponent.
///
/// # Returns
/// A primitive root modulo `p^e`.
///
/// # Panics
/// Panics if `p < 2`, `e = 0`, `p^e` does not fit in `i64`, or `p = 2, e > 2`.
/// The caller must supply a prime `p`.
///
/// # Examples
///
/// ```
/// // For p = 17 and e = 2, we compute a primitive root modulo 289.
/// let p = 17;
/// let e = 2;
/// let g = ntt::primitive_root(p, e);
/// assert_eq!(ntt::mod_exp(g, p*(p-1), p*p), 1);
/// ```
pub fn primitive_root(p: i64, e: u32) -> i64 {
    assert!(p >= 2 && e > 0, "expected a prime and a positive exponent");
    p.checked_pow(e).expect("prime power must fit in i64");
    if p == 2 {
        return match e {
            1 => 1,
            2 => 3,
            _ => panic!("powers of two greater than four have no primitive root"),
        };
    }
    let g = primitive_root_mod_p(p);
    // A primitive root modulo p^2 remains primitive modulo every power of an
    // odd prime. If g fails at p^2, g + p succeeds; adding p^(e-1) does not.
    if e > 1 && mod_exp(g, p - 1, p * p) == 1 {
        g + p
    } else {
        g
    }
}

/// Finds a primitive root modulo a prime p
/// # Arguments
///
/// * `p` - Prime modulus.
///
/// # Returns
/// A primitive root modulo `p`.
fn primitive_root_mod_p(p: i64) -> i64 {
    let phi = p - 1;
    let factors = factorize(phi); // Reusing factorize to get both prime factors and multiplicities
    for g in 2..p {
        // Check if g is a primitive root by checking mod_exp conditions with all prime factors of phi
        if factors.iter().all(|(&q, _)| mod_exp(g, phi / q, p) != 1) {
            return g;
        }
    }
    panic!("no primitive root found; p must be prime")
}

/// the Chinese remainder theorem for two moduli
/// # Arguments
///
/// * `a1` - First residue.
/// * `n1` - First modulus.
/// * `a2` - Second residue.
/// * `n2` - Second modulus.
///
/// # Returns
/// The solution to the system of congruences x = a1 (mod n1) and x = a2 (mod n2).
///
/// # Panics
/// Panics unless the moduli are positive and coprime and their product fits in `i64`.
pub fn crt(a1: i64, n1: i64, a2: i64, n2: i64) -> i64 {
    assert!(n1 > 0 && n2 > 0, "CRT moduli must be positive");
    n1.checked_mul(n2).expect("CRT modulus must fit in i64");
    let a1 = a1.rem_euclid(n1) as i128;
    let a2 = a2.rem_euclid(n2) as i128;
    let inverse = mod_inv(n1, n2) as i128;
    let correction = ((a2 - a1) * inverse).rem_euclid(n2 as i128);
    (a1 + correction * n1 as i128) as i64
}

/// computes an n^th root of unity modulo a composite modulus
/// note we require that an n^th root of unity exists for each multiplicative group modulo p^e
/// use the CRT isomorphism to pull back the list of n^th roots of unity to the composite modulus
/// The cyclic length-n NTT requires an n-th root; a 2n-th root is needed
/// when using a length-2n transform to multiply zero-padded inputs.
/// # Arguments
///
/// * `modulus` - Odd modulus greater than one. `n` must divide the totient of
///   each prime-power factor.
/// * `n` - Order of the root of unity.
///
/// # Returns
/// The n-th root of unity modulo `modulus`.
pub fn root_of_unity(modulus: i64, n: i64) -> i64 {
    assert!(
        modulus > 1 && modulus % 2 == 1,
        "modulus must be odd and greater than one"
    );
    assert!(n > 0, "root order must be positive");
    let order = usize::try_from(n).expect("root order must fit in usize");
    let factors = factorize(modulus);
    let mut result = 1;
    for (&p, &e) in factors.iter() {
        let omega = omega(p.pow(e), order); // Find primitive nth root of unity mod p^e
        result = crt(result, modulus / p.pow(e), omega, p.pow(e)); // Combine with the running result using CRT
    }
    result
}

/// ensure the root of unity satisfies sum_{j=0}^{n-1} omega^{jk} = 0 for 1 \le k < n
/// # Arguments
///
/// * `omega` - n-th root of unity.
/// * `n` - Order of the root of unity.
/// * `modulus` - Modulus.
///
/// # Returns
/// True if the root satisfies the radix-2 principal-root conditions.
/// Panics for invalid parameters or roots. For `n > 1`, the modulus must be odd;
/// together with `omega^(n/2) = -1`, this ensures orthogonality and invertibility.
pub fn verify_root_of_unity(omega: i64, n: i64, modulus: i64) -> bool {
    assert!(modulus > 1, "modulus must be greater than one");
    assert!(
        n > 0 && (n as u64).is_power_of_two(),
        "transform length must be a nonzero power of two"
    );
    if n == 1 {
        assert_eq!(
            omega.rem_euclid(modulus),
            1,
            "a first root of unity must equal one"
        );
        return true;
    }
    assert!(
        modulus % 2 == 1,
        "radix-2 transforms require an odd modulus"
    );
    assert_eq!(
        mod_exp(omega, n, modulus),
        1,
        "omega is not an n-th root of unity"
    );
    assert_eq!(
        mod_exp(omega, n / 2, modulus),
        modulus - 1,
        "omega^(n/2) must equal -1 modulo the modulus"
    );
    true
}
