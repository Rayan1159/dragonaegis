import asyncio
import time
import argparse

from collections import defaultdict
from colorama import Fore, Back, Style, init
from src.terminal.terminal import Terminal
from src.database.DatabaseManager import DatabaseManager
from src.web import http

class DragonAegis:
    def __init__(self, db_manager: DatabaseManager, log_packets=False, max_connections=5, conn_interval=60, max_packets=100, packet_interval=1):
        self.max_connections = max_connections
        self.conn_interval = conn_interval
        self.max_packets = max_packets
        self.packet_interval = packet_interval
        self.connections = defaultdict(list)
        self.packets = defaultdict(list)
        
        self.allowed_connection = True
        
        self.blocked_ips = set()
        
        self.db_manager = db_manager
        self.cleanup = None
        self.log_packets = log_packets
        
        self.active_connections = defaultdict(int)
        
        self.server_selected = None


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
        
        if rate_limiter.server_selected is not None:     
            if not rate_limiter.allowed_connection:
                print(f"Blocked connection from {client_ip}: connections to server are disabled.")
                writer.close();
            
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
            
            proto_version,proto_bytes = parse_varint(payload[offset:])
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

                                packet = bytes(buffer[:total_length])
                                del buffer[:total_length]

                                if client_state == "play" and rate_limiter.log_packets:
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
                                        next_state = parse_handshake(payload)
                                        if next_state == 2:
                                            client_state = "login"
                                    if packet_id == 0xFE:
                                        pass
                                elif client_state == "login":
                                    if packet_id == 0x00:
                                        username = parse_login_start(payload)
                                        client_state = "play"
                                elif client_state == "play":
                                    if packet_id == 0x07:
                                        if rate_limiter.log_packets:
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
    parser = argparse.ArgumentParser(description='DragonAegis Proxy')
    parser.add_argument('--target-server', type=str, default="", help="Target server to stream socket to")
    parser.add_argument('--target-server-port', type=int, default=0, help="Target server port")
    parser.add_argument('--log-packets', type=bool, default=False, help='Log incoming packets')
    parser.add_argument('--refresh-tables', type=bool, default=False, help='Refresh database tables')
    parser.add_argument('--api-mode', type=bool, default=False, help="Enables the api")

    args = parser.parse_args()

    log_packets = args.log_packets
    refresh_tables = args.refresh_tables
    enable_api = args.api_mode

    if not args.target_server or args.target_server_port:
        print(f"\n{Fore.RED}⚠️ Target server or port not specified {Style.RESET_ALL}")
        exit(-1)

    backend_host = args.target_server
    backend_port = args.target_server_port
    proxy_port = 25565


    if enable_api:
        http.run()

    db_manager = DatabaseManager(
        host='localhost',
        port=3306,
        user="root",
        password="",
        db="dragon",
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

    if not enable_api:
        async with server:
            print(f"Proxy running on port {proxy_port}...")
            await server.serve_forever()
    else:
        print("unable to run socket, api is enabled")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️ Proxy shutting down...{Style.RESET_ALL}")