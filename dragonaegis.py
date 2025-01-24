import asyncio
import time

from io import BytesIO


from collections import defaultdict
from colorama import Fore, Back, Style, init
from src.terminal import Terminal
from src.database.DatabaseManager import DatabaseManager

from src.packets.PacketHandler import PacketHandler

class DragonAegis:
    def __init__(self, db_manager: DatabaseManager, max_connections=5, conn_interval=60, max_packets=100, packet_interval=1):
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
        peername = writer.get_extra_info('peername')
        client_ip = peername[0] if peername else 'unknown'
        
        # Initialize packet handler for this connection
        packet_handler = PacketHandler()
        backend_reader = None
        backend_writer = None

        try:
            # Connect to backend Minecraft server
            backend_reader, backend_writer = await asyncio.open_connection(backend_host, backend_port)
            
            # Initial handshake
            handshake_data = await reader.read(4096)
            backend_writer.write(handshake_data)
            await backend_writer.drain()

            # Handle login sequence
            login_response = await backend_reader.read(4096)
            writer.write(login_response)
            await writer.drain()

            # Handle encryption setup
            encryption_data = await backend_reader.read(4096)
            if encryption_data:
                # Parse encryption request (Packet ID 0x01)
                _, packet_id, payload = packet_handler.read_packet(encryption_data)
                if packet_id == 0x01:
                    # Implement proper encryption handshake here
                    # For now, just forward the packet
                    writer.write(encryption_data)
                    await writer.drain()

            # Set up bidirectional forwarding
            async def forward(src, dest, handler, is_client=True):
                try:
                    while True:
                        # Read packet length
                        length_data = await src.readexactly(1)
                        length = handler.read_varint(BytesIO(length_data))
                        
                        # Read full packet
                        packet_data = await src.readexactly(length)
                        full_packet = length_data + packet_data

                        if is_client:
                            # Handle client commands
                            decrypted = handler.decrypt_packet(full_packet)
                            _, packet_id, payload = handler.read_packet(decrypted)
                            if packet_id == 0x03:  # Chat message packet
                                message = payload.decode('utf-8')
                                if message.startswith('/proxy'):
                                    response = "§a[Proxy] Command executed!\n"
                                    response_packet = handler.create_packet(0x0E, response.encode())
                                    writer.write(handler.encrypt_packet(response_packet))
                                    await writer.drain()
                                    continue
                        # Forward packet
                        dest.write(handler.encrypt_packet(full_packet))
                        await dest.drain()
                except (asyncio.IncompleteReadError, ConnectionResetError):
                    pass

            # Create forwarding tasks
            client_to_server = forward(reader, backend_writer, packet_handler, is_client=True)
            server_to_client = forward(backend_reader, writer, packet_handler, is_client=False)

            await asyncio.gather(client_to_server, server_to_client)

        except Exception as e:
            print(f"Connection error ({client_ip}): {e}")
        finally:
            # Clean up connections properly
            if backend_writer and not backend_writer.is_closing():
                backend_writer.close()
                await backend_writer.wait_closed()
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()

    def get_connections(self):
        return self.active_connections

async def main():
    backend_host = 'localhost'  
    backend_port = 25565       
    proxy_port = 25566          

    db_manager = DatabaseManager(
        host='localhost',
        port=3306,
        user="aegis",
        password="debug",
        db="aegis"
    )
    await db_manager.initialize()

    rate_limiter = DragonAegis(
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
    asyncio.run(main())