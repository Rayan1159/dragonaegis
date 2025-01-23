import asyncio
import time

from collections import defaultdict
from colorama import Fore, Back, Style, init
from src.terminal import Terminal

class DragonAegis:
    def __init__(self, max_connections=5, conn_interval=60, max_packets=100, packet_interval=1):
        self.max_connections = max_connections
        self.conn_interval = conn_interval
        self.max_packets = max_packets
        self.packet_interval = packet_interval
        self.connections = defaultdict(list)
        self.packets = defaultdict(list)
        
        self.blocked_ips = set()
        self.active_connections = defaultdict(int)

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

        async def forward(src, dest, is_client=True):
            try:
                while True:
                    data = await src.read(4096)
                    if not data:
                        break
                    if is_client and not rate_limiter.is_allowed_packet(client_ip):
                        print(f"Blocked {client_ip} for packet spam.")
                        break
                    if client_ip in rate_limiter.blocked_ips:
                        print(f"Blocked connection from {client_ip}: IP is blocked.")
                        break
                    dest.write(data)
                    await dest.drain()
            except:
                pass
            finally:
                await dest.drain()
                dest.close()
                


        client_to_backend = forward(reader, backend_writer, is_client=True)
        backend_to_client = forward(backend_reader, writer, is_client=False)

        await asyncio.gather(client_to_backend, backend_to_client)
        writer.close()
        await writer.wait_closed()
        backend_writer.close()
        await backend_writer.wait_closed()
        
    def get_connections(self):
        return self.active_connections

async def main():
    backend_host = 'localhost'  
    backend_port = 25565       
    proxy_port = 25566          

    rate_limiter = DragonAegis(
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
    
    terminal = Terminal()
    
    asyncio.create_task(terminal.terminal_loop(rate_limiter))

    async with server:
        print(f"Proxy running on port {proxy_port}...")
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())