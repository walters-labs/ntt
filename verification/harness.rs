//! Fixed-size entry points for SAW; each calls the production public API.
//! Compiled only for tests and mir-json's `cfg(crux)` build.

#[allow(dead_code)]
pub fn forward_8_17(a: [i64; 8]) -> [i64; 8] {
    let result = crate::ntt(&a, 9, 8, 17);
    let mut out = [0; 8];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn inverse_8_17(a: [i64; 8]) -> [i64; 8] {
    let result = crate::intt(&a, 9, 8, 17);
    let mut out = [0; 8];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn multiply_8_17(a: [i64; 8], b: [i64; 8]) -> [i64; 8] {
    let result = crate::polymul_ntt(&a, &b, 8, 17, 9);
    let mut out = [0; 8];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn forward_16_17(a: [i64; 16]) -> [i64; 16] {
    let result = crate::ntt(&a, 3, 16, 17);
    let mut out = [0; 16];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn inverse_16_17(a: [i64; 16]) -> [i64; 16] {
    let result = crate::intt(&a, 3, 16, 17);
    let mut out = [0; 16];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn multiply_16_17(a: [i64; 16], b: [i64; 16]) -> [i64; 16] {
    let result = crate::polymul_ntt(&a, &b, 16, 17, 3);
    let mut out = [0; 16];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn forward_8_289(a: [i64; 8]) -> [i64; 8] {
    let result = crate::ntt(&a, 110, 8, 289);
    let mut out = [0; 8];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn inverse_8_289(a: [i64; 8]) -> [i64; 8] {
    let result = crate::intt(&a, 110, 8, 289);
    let mut out = [0; 8];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn multiply_8_289(a: [i64; 8], b: [i64; 8]) -> [i64; 8] {
    let result = crate::polymul_ntt(&a, &b, 8, 289, 110);
    let mut out = [0; 8];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn forward_256_12289(a: [i64; 256]) -> [i64; 256] {
    let result = crate::ntt(&a, 8340, 256, 12289);
    let mut out = [0; 256];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn inverse_256_12289(a: [i64; 256]) -> [i64; 256] {
    let result = crate::intt(&a, 8340, 256, 12289);
    let mut out = [0; 256];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn multiply_256_12289(a: [i64; 256], b: [i64; 256]) -> [i64; 256] {
    let result = crate::polymul_ntt(&a, &b, 256, 12289, 8340);
    let mut out = [0; 256];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn forward_1024_12289(a: [i64; 1024]) -> [i64; 1024] {
    let result = crate::ntt(&a, 10302, 1024, 12289);
    let mut out = [0; 1024];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn inverse_1024_12289(a: [i64; 1024]) -> [i64; 1024] {
    let result = crate::intt(&a, 10302, 1024, 12289);
    let mut out = [0; 1024];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn multiply_1024_12289(a: [i64; 1024], b: [i64; 1024]) -> [i64; 1024] {
    let result = crate::polymul_ntt(&a, &b, 1024, 12289, 10302);
    let mut out = [0; 1024];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn forward_2048_12289(a: [i64; 2048]) -> [i64; 2048] {
    let result = crate::ntt(&a, 1945, 2048, 12289);
    let mut out = [0; 2048];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn inverse_2048_12289(a: [i64; 2048]) -> [i64; 2048] {
    let result = crate::intt(&a, 1945, 2048, 12289);
    let mut out = [0; 2048];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn multiply_2048_12289(a: [i64; 2048], b: [i64; 2048]) -> [i64; 2048] {
    let result = crate::polymul_ntt(&a, &b, 2048, 12289, 1945);
    let mut out = [0; 2048];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn forward_2048_151019521(a: [i64; 2048]) -> [i64; 2048] {
    let result = crate::ntt(&a, 51689479, 2048, 151019521);
    let mut out = [0; 2048];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn inverse_2048_151019521(a: [i64; 2048]) -> [i64; 2048] {
    let result = crate::intt(&a, 51689479, 2048, 151019521);
    let mut out = [0; 2048];
    out.copy_from_slice(&result);
    out
}

#[allow(dead_code)]
pub fn multiply_2048_151019521(a: [i64; 2048], b: [i64; 2048]) -> [i64; 2048] {
    let result = crate::polymul_ntt(&a, &b, 2048, 151019521, 51689479);
    let mut out = [0; 2048];
    out.copy_from_slice(&result);
    out
}
