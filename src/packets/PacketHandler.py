from io import BytesIO
from Crypto.Cipher import AES
import struct
import zlib

class PacketHandler:
    def __init__(self):
        self.compression_threshold = -1
        self.encryption_enabled = False
        self.cipher = None
        self.shared_secret = None
        
    def read_varint(self, data: bytes) -> tuple[int, int]:
        """Read VarInt from bytes, returns (value, bytes_consumed)"""
        value = 0
        shift = 0
        index = 0
        while index < len(data):
            byte = data[index]
            value |= (byte & 0x7F) << shift
            shift += 7
            index += 1
            if not (byte & 0x80):
                break
        return value, index

    def read_packet(self, data: bytes) -> tuple[int, int, bytes]:
        """Parse packet from raw bytes"""
        # Read packet length
        length, consumed = self.read_varint(data)
        remaining = data[consumed:]
        
        # Read packet ID
        packet_id, id_consumed = self.read_varint(remaining)
        
        # Get payload (remaining bytes after packet ID)
        payload = remaining[id_consumed:id_consumed + (length - id_consumed)]
        
        return length, packet_id, payload
        
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

    def read_varint(self, buffer):
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

    def write_varint(self, value):
        data = bytearray()
        while True:
            byte = value & 0x7F
            value >>= 7
            data.append(byte | (0x80 if value > 0 else 0))
            if value == 0:
                break
        return bytes(data)  # THIS WAS MISSING
    
    def decrypt_packet(self, data):
        if self.encryption_enabled:
            return self.cipher.decrypt(data)
        return data

    def encrypt_packet(self, data):
        if self.encryption_enabled:
            return self.cipher.encrypt(data)
        return data
    
    def decompress_packet(self, data):
        if self.compression_threshold == -1:
            return data
            
        buffer = BytesIO(data)
        data_length = self.read_varint(buffer)
        
        if data_length == 0:  # Uncompressed
            return buffer.read()
            
        # Use raw DEFLATE format (-15 window bits)
        decompress_obj = zlib.decompressobj(wbits=-zlib.MAX_WBITS)
        decompressed = decompress_obj.decompress(buffer.read())
        decompressed += decompress_obj.flush()
        return decompressed

    def compress_packet(self, data):
        if self.compression_threshold == -1 or len(data) < self.compression_threshold:
            return self.write_varint(0) + data
            
        # Use raw DEFLATE format
        compress_obj = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        compressed = compress_obj.compress(data)
        compressed += compress_obj.flush()
        return self.write_varint(len(data)) + compressed

    # Add these helper methods
    def read_string(self, buffer):
        length = self.read_varint(buffer)
        return buffer.read(length).decode('utf-8')

    def read_byte_array(self, buffer):
        length = self.read_varint(buffer)
        return buffer.read(length)