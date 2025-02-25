from colorama import Fore, Back, Style, init
from collections import defaultdict
import asyncio

from src.database.DatabaseManager import DatabaseManager

import aioconsole

class Terminal:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._timeout_task = None
        self.session_timeout = 15 # 15 minutes in seconds

    async def get_server(self):
        server_ip, server_port = self.server_selected.split(":")
        return await self.db_manager.get_server_id(server_ip, int(server_port))
    
    async def _reset_session_timeout(self): 
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
        self._timeout_task = asyncio.create_task(self._session_timeout_handler())

    async def _session_timeout_handler(self):
        await asyncio.sleep(self.session_timeout)
        self.server_selected = None
        self._timeout_task = None
        print(f"\n{Fore.YELLOW}⚠️ Session timed out due to inactivity. Server selection reset.{Style.RESET_ALL}")

    async def terminal_loop(self, rate_limiter):
        help_text = f"""
            {Fore.CYAN}📖 Available Commands:{Style.RESET_ALL}
            {Fore.GREEN}/allow-con <true>:<false>{Fore.WHITE} - Allows or disallows all connections to the selected server
            {Fore.GREEN}/connections{Fore.WHITE}    - Show active connections
            {Fore.GREEN}/block <IP>{Fore.WHITE}     - Block an IP address
            {Fore.GREEN}/unblock <IP>{Fore.WHITE}   - Unblock an IP address
            {Fore.GREEN}/blocked{Fore.WHITE}       - List blocked IPs
            {Fore.GREEN}/help{Fore.WHITE}          - Show this help
            {Fore.RED}/exit{Fore.WHITE}          - Shutdown the proxy{Style.RESET_ALL}
        """

        while True:
            prompt = (f"{Fore.BLUE}⚡ {Style.BRIGHT}Proxy{Fore.CYAN}»{Style.RESET_ALL} "
                      if rate_limiter.server_selected is not None
                      else f"{Fore.BLUE}⚡ {Style.BRIGHT}No server selected{Fore.RED}»{Style.RESET_ALL} ")
            try:
                cmd = await aioconsole.ainput(prompt)
                if not cmd:
                    continue

                parts = cmd.split()
                
                if rate_limiter.server_selected is not None:
                    if parts[0] == "/connections":
                        server_id = self.get_server()
                        
                        if not server_id:
                            print("No server selected or found.")
                            return;
                        
                        print(f"\n{Fore.CYAN}🔗 Active Connections:{Style.RESET_ALL}")
                        print(await self.db_manager.get_connection_count(rate_limiter.server_selected.split(":")[0], server_id))
                        await self._reset_session_timeout()
                    elif parts[0] == "/block" and len(parts) > 1:
                        rate_limiter.block_ip(parts[1])
                        print(f"{Fore.RED}🔒 Blocked {Fore.YELLOW}{parts[1]}{Style.RESET_ALL}")
                        await self._reset_session_timeout()
                    
                    elif parts[0] == "/unblock" and len(parts) > 1:
                        rate_limiter.unblock_ip(parts[1])
                        print(f"{Fore.GREEN}🔓 Unblocked {Fore.YELLOW}{parts[1]}{Style.RESET_ALL}")
                        await self._reset_session_timeout()
                    
                    elif parts[0] == "/blocked":
                        blocked = rate_limiter.list_blocked()
                        print(f"\n{Fore.RED}🚫 Blocked IPs ({len(blocked)}):{Style.RESET_ALL}")
                        for ip in blocked:
                            print(f"  {Fore.YELLOW}{ip}{Style.RESET_ALL}")
                        print()
                        await self._reset_session_timeout()
                    
                    elif parts[0] == "/help":                          
                        print(help_text)
                        await self._reset_session_timeout()
                    
                    elif parts[0] == "/allow-con":
                        if parts[1] == "true":
                            print(f"\n{Fore.CYAN}🔓 Allowing all connections to server {rate_limiter.server_selected}...{Style.RESET_ALL}")
                            rate_limiter.allowed_connection(rate_limiter.server_selected) = True
                        elif parts[1] == "false":
                            print(f"\n{Fore.RED}🔒 Blocking all connections to server {rate_limiter.server_selected}...{Style.RESET_ALL}")
                            rate_limiter.allowed_connection(rate_limiter.server_selected) = False
                    elif parts[0] == "/exit":
                        print(f"\n{Fore.MAGENTA}🌸 Shutting down proxy...{Style.RESET_ALL}")
                        exit(0)
                    else:
                        print(f"{Fore.RED}❌ Unknown command. Type {Fore.WHITE}/help{Fore.RED} for assistance.{Style.RESET_ALL}")
                else:
                    if parts and parts[0] == "/select":
                        if len(parts) < 2:
                            print(f"{Fore.RED}❌ Missing server address. Use /select <ip>:<port>{Style.RESET_ALL}")
                            continue
                        server_address = parts[1]
                        if ":" in server_address:
                            rate_limiter.server_selected = server_address
                            print(f"{Fore.GREEN}🎯 Selected server: {Fore.YELLOW}{rate_limiter.server_selected}{Style.RESET_ALL}")
                            await self._reset_session_timeout()
                        else:
                            print(f"{Fore.RED}❌ Invalid IP format. Use <ip>:<port>{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}❌ No server selected. Type {Fore.WHITE}/select <ip>:<port>{Fore.RED} to select a server.{Style.RESET_ALL}")

            except Exception as e:
                print(f"{Fore.RED}💥 Command error: {Fore.WHITE}{e}{Style.RESET_ALL}")