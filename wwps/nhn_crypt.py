import gzip
import hashlib
from base64 import b64decode, b64encode

from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad

NHN_KEY = bytes([0xa8, 0x65, 0xd7, 0xe5, 0xe2, 0x45, 0x8f, 0x8c,
                 0xe1, 0xb5, 0xec, 0xd0, 0x87, 0xe5, 0x45, 0x94])
DIGEST_SALT = b"0bk2kvtFE2"


def decrypt_request(content: str) -> str:
    data = content.replace('-', '+').replace('_', '/')
    pad_len = (-len(data)) % 4
    data += "=" * pad_len
    raw = b64decode(data)
    decrypted = unpad(AES.new(NHN_KEY, AES.MODE_ECB).decrypt(raw), AES.block_size)
    return decrypted[20:].decode("utf-8")


def encrypt_response(decrypted_content: str) -> str:
    compressed = gzip.compress(decrypted_content.encode("utf-8"))
    digest = _calc_digest(compressed)
    padded = pad(digest + compressed, AES.block_size)
    encrypted = AES.new(NHN_KEY, AES.MODE_ECB).encrypt(padded)
    return b64encode(encrypted).decode("ascii").replace('+', '-').replace('/', '_')


def _calc_digest(content: bytes) -> bytes:
    first = hashlib.sha1(DIGEST_SALT + b' ' + content).digest()
    return hashlib.sha1(DIGEST_SALT + first).digest()
