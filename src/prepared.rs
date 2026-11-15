use crate::{mod_add, mod_inv, mod_mul, mod_normalize, mod_sub, verify_root_of_unity};

/// Validated parameters and reusable twiddle factors for a radix-2 NTT.
///
/// Transforms operate on coefficient slices without allocating. Forward output
/// and inverse input use bit-reversed order. All outputs lie in `0..modulus`.
/// This implementation does not claim constant-time execution.
///
/// ```
/// use ntt::PreparedNtt;
/// let transform = PreparedNtt::new(8, 17, ntt::omega(17, 8));
/// let mut coefficients = [1, 2, 3, 4, 0, 0, 0, 0];
/// let original = coefficients;
/// transform.forward_in_place(&mut coefficients);
/// transform.inverse_in_place(&mut coefficients);
/// assert_eq!(coefficients, original);
/// ```
#[derive(Clone, Debug)]
pub struct PreparedNtt {
    n: usize,
    modulus: i64,
    inverse_length: i64,
    forward_twiddles: Vec<i64>,
    inverse_twiddles: Vec<i64>,
}

impl PreparedNtt {
    /// Construct a transform using a supplied root, without factoring the modulus.
    ///
    /// # Panics
    /// Panics unless `n` is a nonzero power of two fitting in `i64`, `modulus > 1`,
    /// and `omega` is a suitable principal root. For `n > 1`, the modulus must be
    /// odd and `omega^(n/2) = -1 (mod modulus)`; for `n = 1`, `omega = 1`.
    /// These conditions also ensure that `n` and `omega` have modular inverses.
    /// All positive `i64` moduli satisfying these conditions are supported.
    pub fn new(n: usize, modulus: i64, omega: i64) -> Self {
        let order = i64::try_from(n).expect("transform length must fit in i64");
        verify_root_of_unity(omega, order, modulus);
        let omega = omega.rem_euclid(modulus);
        let inverse_root = mod_inv(omega, modulus);
        let mut forward_twiddles = Vec::with_capacity(n / 2);
        let mut inverse_twiddles = Vec::with_capacity(n / 2);
        let (mut forward, mut inverse) = (1, 1);
        for _ in 0..n / 2 {
            forward_twiddles.push(forward);
            inverse_twiddles.push(inverse);
            forward = mod_mul(forward, omega, modulus);
            inverse = mod_mul(inverse, inverse_root, modulus);
        }
        Self {
            n,
            modulus,
            inverse_length: mod_inv(order, modulus),
            forward_twiddles,
            inverse_twiddles,
        }
    }

    /// Number of coefficients in each transform.
    pub fn size(&self) -> usize {
        self.n
    }

    /// Coefficient modulus.
    pub fn modulus(&self) -> i64 {
        self.modulus
    }

    /// Transform coefficients in place, producing bit-reversed output.
    ///
    /// Coefficients may be any `i64` and are normalized before transformation.
    /// Panics if `coefficients.len() != self.size()`, before modifying the slice.
    pub fn forward_in_place(&self, coefficients: &mut [i64]) {
        self.check_length(coefficients);
        forward_transform(coefficients, &self.forward_twiddles, self.modulus);
    }

    /// Invert a transform in place, consuming bit-reversed input.
    ///
    /// Coefficients may be any `i64` and are normalized before transformation.
    /// Panics if `coefficients.len() != self.size()`, before modifying the slice.
    pub fn inverse_in_place(&self, coefficients: &mut [i64]) {
        self.check_length(coefficients);
        inverse_transform(
            coefficients,
            &self.inverse_twiddles,
            self.modulus,
            self.inverse_length,
        );
    }

    /// Multiply modulo `x^n - 1` and the coefficient modulus.
    ///
    /// Allocates two coefficient buffers and reuses the transform's twiddle factors.
    /// Panics unless both inputs have exactly `self.size()` coefficients.
    pub fn multiply(&self, a: &[i64], b: &[i64]) -> Vec<i64> {
        self.check_length(a);
        self.check_length(b);
        let mut a = a.to_vec();
        let mut b = b.to_vec();
        self.forward_in_place(&mut a);
        self.forward_in_place(&mut b);
        for (a_i, b_i) in a.iter_mut().zip(b) {
            *a_i = mod_mul(*a_i, b_i, self.modulus);
        }
        self.inverse_in_place(&mut a);
        a
    }

    fn check_length(&self, coefficients: &[i64]) {
        assert_eq!(
            coefficients.len(),
            self.n,
            "input length must equal the transform length"
        );
    }
}

// Slice kernels make the production loops available as compositional proof
// boundaries. Their callers provide validated parameters and twiddle tables.
fn forward_transform(coefficients: &mut [i64], twiddles: &[i64], modulus: i64) {
    for coefficient in coefficients.iter_mut() {
        *coefficient = mod_normalize(*coefficient, modulus);
    }
    let mut step = coefficients.len() / 2;
    while step > 0 {
        forward_stage(coefficients, twiddles, step, modulus);
        step /= 2;
    }
}

fn inverse_transform(
    coefficients: &mut [i64],
    twiddles: &[i64],
    modulus: i64,
    inverse_length: i64,
) {
    for coefficient in coefficients.iter_mut() {
        *coefficient = mod_normalize(*coefficient, modulus);
    }
    let mut step = 1;
    while step < coefficients.len() {
        inverse_stage(coefficients, twiddles, step, modulus);
        step *= 2;
    }
    for coefficient in coefficients {
        *coefficient = mod_mul(*coefficient, inverse_length, modulus);
    }
}

#[inline]
fn forward_stage(coefficients: &mut [i64], twiddles: &[i64], step: usize, modulus: i64) {
    let stride = coefficients.len() / (2 * step);
    for block in coefficients.chunks_exact_mut(2 * step) {
        let (left, right) = block.split_at_mut(step);
        for j in 0..step {
            (left[j], right[j]) =
                forward_butterfly(left[j], right[j], twiddles[j * stride], modulus);
        }
    }
}

#[inline]
fn inverse_stage(coefficients: &mut [i64], twiddles: &[i64], step: usize, modulus: i64) {
    let stride = coefficients.len() / (2 * step);
    for block in coefficients.chunks_exact_mut(2 * step) {
        let (left, right) = block.split_at_mut(step);
        for j in 0..step {
            (left[j], right[j]) =
                inverse_butterfly(left[j], right[j], twiddles[j * stride], modulus);
        }
    }
}

#[inline]
fn forward_butterfly(u: i64, v: i64, twiddle: i64, modulus: i64) -> (i64, i64) {
    (
        mod_add(u, v, modulus),
        mod_mul(mod_sub(u, v, modulus), twiddle, modulus),
    )
}

#[inline]
fn inverse_butterfly(u: i64, v: i64, twiddle: i64, modulus: i64) -> (i64, i64) {
    let v = mod_mul(v, twiddle, modulus);
    (mod_add(u, v, modulus), mod_sub(u, v, modulus))
}
