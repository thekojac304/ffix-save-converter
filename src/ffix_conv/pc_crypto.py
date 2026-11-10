"""AES-256-CBC used by the 2016 PC release for SavedData_ww.dat.

Key/IV derivation (PBKDF2-HMAC-SHA1, password "System.Security.SecureString",
salt 03 03 01 04 07 00 09 07, 1000 iterations, 48 bytes -> key[32] + iv[16])
is documented by Memoria (MIT) and independently by ff9SaveLib / ffix-save-editor.
Every encrypted section uses the same key and IV, so encryption is deterministic.
"""
import functools
import hashlib

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PASSWORD = b"System.Security.SecureString"
SALT = bytes([3, 3, 1, 4, 7, 0, 9, 7])


class DecryptError(ValueError):
    pass


@functools.lru_cache(maxsize=1)
def key_iv():
    d = hashlib.pbkdf2_hmac("sha1", PASSWORD, SALT, 1000, 48)
    return d[:32], d[32:]


def cipher_size(plain_size):
    """PKCS7 always adds 1..16 bytes."""
    return plain_size + 16 - plain_size % 16


def encrypt(plain):
    key, iv = key_iv()
    p = padding.PKCS7(128).padder()
    data = p.update(plain) + p.finalize()
    e = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return e.update(data) + e.finalize()


def decrypt(cipher):
    if len(cipher) == 0 or len(cipher) % 16:
        raise DecryptError("ciphertext length is not a positive multiple of 16")
    key, iv = key_iv()
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    data = d.update(cipher) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    try:
        return u.update(data) + u.finalize()
    except ValueError as e:
        raise DecryptError("bad PKCS7 padding (wrong key or corrupt data)") from e
