import hashlib
import secrets
import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


def generate_session_key():
    """Generate 256-bit AES key"""
    return secrets.token_hex(32)


def compute_hash(data: bytes):
    """Compute SHA-256 hash"""
    return hashlib.sha256(data).hexdigest()


def encrypt_aes(data: bytes, key_hex: str):
    """Encrypt data using AES-256-GCM"""
    key = bytes.fromhex(key_hex)
    iv = secrets.token_bytes(12)
    
    encryptor = Cipher(
        algorithms.AES(key),
        modes.GCM(iv),
        backend=default_backend()
    ).encryptor()
    
    ciphertext = encryptor.update(data) + encryptor.finalize()
    
    return {
        "ciphertext": ciphertext.hex(),
        "iv": iv.hex(),
        "tag": encryptor.tag.hex()
    }


def decrypt_aes(enc_data, key_hex: str):
    """Decrypt data using AES-256-GCM"""
    key = bytes.fromhex(key_hex)
    iv = bytes.fromhex(enc_data["iv"])
    tag = bytes.fromhex(enc_data["tag"])
    ciphertext = bytes.fromhex(enc_data["ciphertext"])
    
    decryptor = Cipher(
        algorithms.AES(key),
        modes.GCM(iv, tag),
        backend=default_backend()
    ).decryptor()
    
    return decryptor.update(ciphertext) + decryptor.finalize()


def generate_rsa_keys():
    """Generate RSA-2048 key pair"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    return private_key, public_key


def serialize_public_key(public_key):
    """Convert public key to PEM format"""
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem.decode('utf-8')


def sign_hash(private_key, hash_text: str):
    """Sign hash with RSA private key"""
    signature = private_key.sign(
        hash_text.encode('utf-8'),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')


def verify_signature(public_key, signature_b64: str, hash_text: str):
    """Verify RSA signature"""
    try:
        public_key.verify(
            base64.b64decode(signature_b64),
            hash_text.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False
