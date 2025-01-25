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

    def read_varint(self, buf, start):
        # Simple VarInt parser
        value = 0
        shift = 0
        length = 0
        while True:
            b = buf[start + length]
            length += 1
            value |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        return value, length
    
    def build_string(self, value):
        # VarInt length + UTF-8 data
        data = value.encode('utf-8')
        return self.build_varint(len(data)) + data
        
    def build_varint_length(self, length):
    # Returns a varint representing the length of the packet
        buf = bytearray()
        while True:
            temp = length & 0x7F
            length >>= 7
            if length != 0:
                temp |= 0x80
            buf.append(temp)
            if length == 0:
                break
        return buf
    
    def parse_varint(data):
        value = 0
        length = 0
        for i in range(len(data)):
            byte = data[i]
            value |= (byte & 0x7F) << (7 * i)
            length += 1
            if (byte & 0x80) == 0:
                break
        return value, length
    
    def parse_handshake(self, payload):
    # Handshake structure: protocol_version (VarInt), server_addr (String), port (Unsigned Short), next_state (VarInt)
        offset = 0
        # Protocol version
        proto_version, proto_bytes = self.parse_varint(payload[offset:])
        offset += proto_bytes
        # Server address (string)
        addr_length = payload[offset]
        offset += 1
        server_addr = payload[offset:offset+addr_length].decode('utf-8')
        offset += addr_length
        # Port (unsigned short)
        port = int.from_bytes(payload[offset:offset+2], byteorder='big')
        offset += 2
        # Next state
        next_state, _ = self.parse_varint(payload[offset:])
        return next_state

    def parse_login_start(payload):
        # Login Start structure: username (String)
        username_length = payload[0]
        username = payload[1:1+username_length].decode('utf-8')
        return username
    
    def build_varint(self, value):
        out = bytearray()
        while True:
            temp = value & 0x7F
            value >>= 7
            if value != 0:
                temp |= 0x80
            out.append(temp)
            if value == 0:
                break
        # Build the length prefix
        length_prefix = len(out)
        return self.build_varint_length(length_prefix) + out

    async def perform_handshake_and_login(self, writer, backend_host, backend_port):
        # Example handshake packet sending (for demonstration; protocol specifics vary by version)
        # Format: [Length VarInt][PacketID VarInt][Protocol Version VarInt][Server Address String][Server Port Unsigned Short][Next State VarInt]
        protocol_version = 763  # Example for 1.20.4
        packet_id = 0x00
        
        # Build handshake packet
        handshake_data = self.build_varint(len(backend_host) + 7) + self.build_varint(packet_id) + \
                        self.build_varint(protocol_version) + self.build_string(backend_host) + \
                        backend_port.to_bytes(2, byteorder="big") + self.build_varint(2)  # 2 = login
        # Send handshake
        writer.write(handshake_data)
        await writer.drain()

        # Send login start packet
        # [Length VarInt][PacketID VarInt][Username String]
        login_data = self.build_varint(3 + len("Player")) + self.build_varint(0x00) + self.build_string("Player")
        writer.write(login_data)
        await writer.drain()

    def parse_player_chat_packet(self, data):
        # Example parser for packet ID 0x3B in 1.20.4
        offset = 0
        packet_id = data[offset]
        offset += 1
        if packet_id != 0x3B:
            return None
        
        # Read Sender UUID (16 bytes)
        sender_uuid_bytes = data[offset:offset+16]
        offset += 16
        sender_uuid = uuid.UUID(bytes=sender_uuid_bytes)

        # Read Index (VarInt)
        index, varint_length = self.read_varint(data[offset:])
        offset += varint_length

        # Read optional message signature (256 bytes if present)
        # (In practice, use your own logic to detect presence)
        signature = data[offset:offset+256]
        offset += 256

        # Read message (VarInt length + UTF-8 string)
        message_length, ml_len = self.read_varint(data, offset)
        offset += ml_len
        message = data[offset:offset+message_length].decode('utf-8', errors='replace')
        offset += message_length
        
        # Read timestamp (8 bytes)
        timestamp = int.from_bytes(data[offset:offset+8], byteorder='big', signed=True)
        offset += 8

        # Read salt (8 bytes)
        salt = int.from_bytes(data[offset:offset+8], byteorder='big', signed=True)
        offset += 8

        # Parse additional optional fields as needed
        
        return {
            "sender_uuid": str(sender_uuid),
            "index": index,
            "signature": signature,
            "message": message,
            "timestamp": timestamp,
            "salt": salt
        }

    
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