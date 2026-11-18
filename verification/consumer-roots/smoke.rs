#[test]
fn actual_consumer_defaults_select_verified_roots() {
    let module = module_lwe::utils::Parameters::default();
    assert_eq!((2 * module.n, module.q, module.omega), (1024, 12289, 10302));
    let ring = ring_lwe::utils::Parameters::default();
    assert_eq!((2 * ring.n, ring.q, ring.omega), (2048, 12289, 1945));
}
