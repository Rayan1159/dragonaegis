import asyncio
import time

from collections import defaultdict
from colorama import Fore, Back, Style, init
from src.terminal import Terminal
from src.database.DatabaseManager import DatabaseManager
from src.packets.PacketHandler import PacketHandler
import argparse

class DragonAegis:
    def __init__(self, db_manager: DatabaseManager, log_packets=False, max_connections=5, conn_interval=60, max_packets=100, packet_interval=1):
        self.max_connections = max_connections
        self.conn_interval = conn_interval
        self.max_packets = max_packets
        self.packet_interval = packet_interval
        self.connections = defaultdict(list)
        self.packets = defaultdict(list)
        
        self.blocked_ips = set()
        self.active_connections = defaultdict(int)
        
        self.db_manager = db_manager
        self.cleanup = None
        self.log_packets = log_packets

    async def cleanup_task(self) -> None:
        self.cleanup = asyncio.create_task(self._periodic_cleanup())
        
    async def _periodic_cleanup(self) -> None:
         while True:
            await self.db_manager.cleanup_old_entries()
            await asyncio.sleep(3600)

    def is_allowed_connection(self, ip):
        now = time.time()
        self.connections[ip] = [t for t in self.connections[ip] if now - t < self.conn_interval]
        if len(self.connections[ip]) >= self.max_connections:
            return False
        self.connections[ip].append(now)
        self.active_connections[ip] += 1
        return True

    def is_allowed_packet(self, ip):
        now = time.time()
        self.packets[ip] = [t for t in self.packets[ip] if now - t < self.packet_interval]
        if len(self.packets[ip]) >= self.max_packets:
            return False
        self.packets[ip].append(now)
        return True

    def block_ip(self, ip):
        self.blocked_ips.add(ip)

    def unblock_ip(self, ip):
        self.blocked_ips.discard(ip)

    def list_blocked(self):
        return list(self.blocked_ips)

    async def handle_client(reader, writer, backend_host, backend_port, rate_limiter):
        transport = writer.transport
        peername = transport.get_extra_info('peername')
        client_ip = peername[0] if peername else 'unknown'

        client_state = "handshake"
        buffer = bytearray()
        username = None

        if not rate_limiter.is_allowed_connection(client_ip):
            print(f"Blocked connection from {client_ip}: too many connections.")
            writer.close()
            await writer.wait_closed()
            return

        try:
            backend_reader, backend_writer = await asyncio.open_connection(backend_host, backend_port)
        except Exception as e:
            print(f"Backend connection failed: {e}")
            writer.close()
            await writer.wait_closed()
            return

        def parse_varint(data):
            value = 0
            length = 0
            for i in range(min(len(data), 5)):
                byte = data[i]
                value |= (byte & 0x7F) << (7 * i)
                length += 1
                if (byte & 0x80) == 0:
                    break
            return value, length

        def parse_handshake(payload):
            offset = 0
            if len(payload) < offset + 1:
                raise ValueError("Incomplete handshake packet")
            proto_version, proto_bytes = parse_varint(payload[offset:])
            offset += proto_bytes
            if len(payload) < offset + 1:
                raise ValueError("Incomplete handshake packet")
            addr_length = payload[offset]
            offset += 1
            if len(payload) < offset + addr_length:
                raise ValueError("Incomplete handshake packet")
            server_addr = payload[offset:offset+addr_length].decode('utf-8')
            offset += addr_length
            if len(payload) < offset + 2:
                raise ValueError("Incomplete handshake packet")
            port = int.from_bytes(payload[offset:offset+2], byteorder='big')
            offset += 2
            if len(payload) < offset + 1:
                raise ValueError("Incomplete handshake packet")
            next_state, _ = parse_varint(payload[offset:])
            return next_state

        def parse_login_start(payload):
            username_length = payload[0]
            return payload[1:1+username_length].decode('utf-8')

        async def forward(src, dest, is_client=True):
            nonlocal client_state, buffer, username
            try:
                while True:
                    data = await src.read(4096)
                    if not data:
                        break

                    if is_client:
                        buffer.extend(data)
                        while True:
                            if len(buffer) < 1:
                                break

                            try:
                                length, length_bytes = parse_varint(buffer)
                                total_length = length_bytes + length

                                if len(buffer) < total_length:
                                    print(f"Waiting for more data (expected {total_length} bytes, got {len(buffer)})")
                                    break

                                packet = bytes(buffer[:total_length])
                                del buffer[:total_length]

                                if rate_limiter.log_packets:    
                                    print(f"Client packet: {packet.hex()}")
                                
                                packet_id, id_bytes = parse_varint(packet[length_bytes:])
                                payload = packet[length_bytes + id_bytes:]

                                if not rate_limiter.is_allowed_packet(client_ip):
                                    print(f"Blocked {client_ip} for packet spam.")
                                    return

                                if client_ip in rate_limiter.blocked_ips:
                                    print(f"Blocked connection from {client_ip}: IP is blocked.")
                                    return

                                if client_state == "handshake":
                                    if packet_id == 0x00:
                                        print(f"Handshake packet detected: {payload.hex()}")
                                        next_state = parse_handshake(payload)
                                        if next_state == 2:
                                            client_state = "login"
                                elif client_state == "login":
                                    if packet_id == 0x00:
                                        username = parse_login_start(payload)
                                        print(f"Player {username} ({client_ip}) is connecting!")
                                        client_state = "play"
                                elif client_state == "play":
                                    if packet_id == 0x07:
                                        print(f"Chat message from {username}: {payload[1:].decode('utf-8')}")
                                        
                                dest.write(packet)
                                await dest.drain()

                            except ValueError as e:
                                print(f"Packet parsing error: {e}")
                                break

                    else:
                        dest.write(data)
                        await dest.drain()
            except Exception as e:
                print(f"Forwarding error: {e}")
            finally:
                dest.close()
                await dest.wait_closed()

        client_to_server = forward(reader, backend_writer, is_client=True)
        server_to_client = forward(backend_reader, writer, is_client=False)
        
        await asyncio.gather(client_to_server, server_to_client)

        writer.close()
        await writer.wait_closed()
        
    def get_connections(self):
        return self.active_connections

async def main():
    backend_host = 'localhost'  
    backend_port = 25565       
    proxy_port = 25566         
    
    parser = argparse.ArgumentParser(description='DragonAegis Proxy')
    parser.add_argument('--log-packets', type=bool, default=False, help='Log incoming packets')
    parser.add_argument('--refresh-tables', type=bool, default=False, help='Refresh database tables')

    args = parser.parse_args()

    log_packets = args.log_packets
    refresh_tables = args.refresh_tables

    db_manager = DatabaseManager(
        host='localhost',
        port=3306,
        user="aegis",
        password="debug",
        db="aegis",
        refresh_tables=refresh_tables
    )
    await db_manager.initialize()

    rate_limiter = DragonAegis(
        log_packets=log_packets,
        db_manager=db_manager,
        max_connections=5,      
        conn_interval=60,
        max_packets=100,      
        packet_interval=1
    )
    
    print(f"\n{Fore.GREEN}🚀 DragonAegis started {Style.RESET_ALL}")
    print(f"{Fore.CYAN}📡 Forwarding to: {Fore.YELLOW}{backend_host}:{backend_port}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}🛡️ Proxy listening on: {Fore.YELLOW}0.0.0.0:{proxy_port}{Style.RESET_ALL}\n")

    server = await asyncio.start_server(
        lambda r, w: DragonAegis.handle_client(r, w, backend_host, backend_port, rate_limiter),
        '0.0.0.0', proxy_port
    )
    
    terminal = Terminal(
        db_manager=db_manager
    )
    
    asyncio.create_task(terminal.terminal_loop(rate_limiter))

    async with server:
        print(f"Proxy running on port {proxy_port}...")
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️ Proxy shutting down...{Style.RESET_ALL}")
