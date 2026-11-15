//! Integration obligations identified in verification/consumers.md.
//! These exercise this checkout of ntt; they do not verify the consumer crates.
use ntt::{mod_exp, omega, polymul_ntt, PreparedNtt};

fn negacyclic_reference(a: &[i64], b: &[i64], q: i64) -> Vec<i64> {
    let n = a.len();
    let mut result = vec![0i128; n];
    for (i, &a_i) in a.iter().enumerate() {
        for (j, &b_j) in b.iter().enumerate() {
            let product = i128::from(a_i.rem_euclid(q)) * i128::from(b_j.rem_euclid(q));
            if i + j < n {
                result[i + j] += product;
            } else {
                result[i + j - n] -= product;
            }
        }
    }
    result
        .into_iter()
        .map(|x| x.rem_euclid(i128::from(q)) as i64)
        .collect()
}

#[test]
fn padded_products_match_consumer_negacyclic_rings() {
    for (degree, q, expected_root) in [
        (512, 12289, 10302),
        (1024, 12289, 1945),
        (1024, 12289 * 12289, 51689479),
    ] {
        let transform_length = 2 * degree;
        let root = omega(q, transform_length);
        // Changing root selection requires updating the fixed proof targets.
        assert_eq!(root, expected_root);
        println!("degree={degree}, transform_length={transform_length}, q={q}, root={root}");
        let mut a: Vec<_> = (0..degree).map(|i| i as i64 * 7919 - q).collect();
        let mut b: Vec<_> = (0..degree).map(|i| q - i as i64 * 104729).collect();
        a[0] = i64::MIN;
        b[0] = i64::MAX;
        let expected = negacyclic_reference(&a, &b, q);
        a.resize(transform_length, 0);
        b.resize(transform_length, 0);
        let product = polymul_ntt(&a, &b, transform_length, q, root);
        let folded: Vec<_> = (0..degree)
            .map(|i| (product[i] - product[i + degree]).rem_euclid(q))
            .collect();
        assert_eq!(folded, expected);
    }
}

#[test]
fn shortened_polynomials_require_a_matching_transform_root() {
    // The consumers store a root for twice the ring degree, but polymul_fast
    // chooses its length from the actual (potentially trimmed) polynomials.
    for degree in [512, 1024] {
        let root = omega(12289, 2 * degree);
        let short_length = 2 * 3usize.next_power_of_two();
        assert!(std::panic::catch_unwind(|| PreparedNtt::new(short_length, 12289, root)).is_err());
        let matching_root = omega(12289, short_length);
        PreparedNtt::new(short_length, 12289, matching_root);
    }
}

#[test]
fn changing_consumer_parameters_requires_recomputing_the_root() {
    // Concrete CLI override examples; both current consumer builders retain
    // their default omega when changing n/q. See the pinned source inventory.
    for (old_degree, new_degree, new_q) in [(512, 256, 7681), (1024, 512, 12289)] {
        let stale_root = omega(12289, 2 * old_degree);
        assert!(std::panic::catch_unwind(|| {
            PreparedNtt::new(2 * new_degree, new_q, stale_root)
        })
        .is_err());
        PreparedNtt::new(2 * new_degree, new_q, omega(new_q, 2 * new_degree));
    }
}

#[test]
fn mlkem_twiddle_powers_match_repeated_multiplication() {
    // All three ML-KEM constructors call mod_exp(17, bit_reverse(i, 7), 3329).
    // Bit reversal permutes 0..128, so this covers every exponent they use.
    let mut expected = 1;
    for exponent in 0..128 {
        assert_eq!(mod_exp(17, exponent, 3329), expected);
        expected = expected * 17 % 3329;
    }
}
