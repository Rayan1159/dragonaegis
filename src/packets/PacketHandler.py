from io import BytesIO
from Crypto.Cipher import AES
import struct

class PacketHandler:
    def __init__(self):
        self.compression_threshold = -1
        self.encryption_enabled = False
        self.cipher = None
        
    def read_packet(self, data):
        """Parse a Minecraft packet into (length, packet_id, payload)"""
        buffer = BytesIO(data)
        
        # Read packet length (VarInt)
        length = self.read_varint(buffer)
        
        # Read packet ID (VarInt)
        packet_id = self.read_varint(buffer)
        
        # Read remaining payload
        payload = buffer.read()
        
        return length, packet_id, payload

    def enable_encryption(self, key):
        self.cipher = AES.new(key, AES.MODE_CFB, iv=key)
        self.encryption_enabled = True

    def decrypt_packet(self, data):
        if self.encryption_enabled:
            return self.cipher.decrypt(data)
        return data

    def encrypt_packet(self, data):
        if self.encryption_enabled:
            return self.cipher.encrypt(data)
        return data

    def read_varint(self, buffer):
        # Implement proper VarInt reading
        value = 0
        shift = 0
        while True:
            byte = buffer.read(1)
            if not byte:
                break
            b = ord(byte)
            value |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        return value