from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
import json
import configparser
import os

# Load config
config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), 'config.ini'))
AES_KEY = config.get('Security', 'AES_KEY', fallback='AttendanceKey16!').encode('utf-8')

def decrypt_payload(encrypted_b64: str) -> dict:
    try:
        encrypted_bytes = base64.b64decode(encrypted_b64)
        cipher = AES.new(AES_KEY, AES.MODE_ECB)
        decrypted_padded = cipher.decrypt(encrypted_bytes)
        decrypted = unpad(decrypted_padded, AES.block_size)
        return json.loads(decrypted.decode('utf-8'))
    except Exception as e:
        print(f"Decryption error: {e}")
        return None
