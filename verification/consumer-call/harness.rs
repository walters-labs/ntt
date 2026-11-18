use polynomial_ring::Polynomial;

macro_rules! consumer_entry {
    ($name:ident, $degree:expr, $q:expr, $root:expr) => {
        pub fn $name(a: [i64; $degree], b: [i64; $degree]) -> Polynomial<i64> {
            let mut modulus = vec![0; $degree + 1];
            modulus[0] = 1;
            modulus[$degree] = 1;
            ring_lwe::utils::polymul_fast(
                &Polynomial::new(a.to_vec()),
                &Polynomial::new(b.to_vec()),
                $q,
                &Polynomial::new(modulus),
                $root,
            )
        }
    };
}

consumer_entry!(multiply_1024_12289, 512, 12289, 10302);
consumer_entry!(multiply_2048_12289, 1024, 12289, 1945);
consumer_entry!(multiply_2048_151019521, 1024, 151019521, 51689479);
