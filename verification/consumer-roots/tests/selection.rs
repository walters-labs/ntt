use ntt_consumer_roots_proof::root_for_parameters;

#[test]
fn agrees_with_existing_generation_at_consumer_parameters() {
    for (q, n) in [(12289, 1024), (12289, 2048), (151019521, 2048)] {
        let root = root_for_parameters(q, n);
        assert_eq!(root, ntt::omega(q, n));
        assert!(ntt::verify_root_of_unity(root, n as i64, q));
    }
}

#[test]
fn other_lengths_and_moduli_keep_the_generator() {
    // Include a known modulus with a different length, and vice versa.
    for (q, n) in [(17, 8), (12289, 8), (12289, 1), (65537, 1024)] {
        assert_eq!(root_for_parameters(q, n), ntt::omega(q, n));
    }
}
