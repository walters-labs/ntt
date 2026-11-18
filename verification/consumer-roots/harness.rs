pub mod roots;
pub use roots::root_for_parameters;

// Keep the actual NTT validator reachable in the linked proof MIR.
pub fn validator(root: i64, length: i64, modulus: i64) -> bool {
    ntt::verify_root_of_unity(root, length, modulus)
}
