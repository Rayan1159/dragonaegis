from colorama import Fore, Back, Style, init
from collections import defaultdict

import aioconsole

class Terminal:
    async def terminal_loop(self, rate_limiter):
        
        prompt = f"{Fore.BLUE}⚡ {Style.BRIGHT}Proxy{Fore.CYAN}»{Style.RESET_ALL} "
        
        help_text = f"""
            {Fore.CYAN}📖 Available Commands:{Style.RESET_ALL}
            {Fore.GREEN}/connections{Fore.WHITE}    - Show active connections
            {Fore.GREEN}/block <IP>{Fore.WHITE}     - Block an IP address
            {Fore.GREEN}/unblock <IP>{Fore.WHITE}   - Unblock an IP address
            {Fore.GREEN}/blocked{Fore.WHITE}       - List blocked IPs
            {Fore.GREEN}/help{Fore.WHITE}          - Show this help
            {Fore.RED}/exit{Fore.WHITE}          - Shutdown the proxy{Style.RESET_ALL}
        """

        while True:
            try:
                cmd = await aioconsole.ainput(prompt)
                if not cmd:
                    continue

                parts = cmd.split()
                if parts[0] == "/connections":
                    print(f"\n{Fore.CYAN}🔗 Active Connections:{Style.RESET_ALL}")
                    for ip, count in rate_limiter.active_connections.items():
                        if count > 0:
                            print(f"  {Fore.YELLOW}{ip}{Fore.WHITE}: {Fore.GREEN}{count}{Style.RESET_ALL}")
                    print()
                
                elif parts[0] == "/block" and len(parts) > 1:
                    rate_limiter.block_ip(parts[1])
                    print(f"{Fore.RED}🔒 Blocked {Fore.YELLOW}{parts[1]}{Style.RESET_ALL}")
                
                elif parts[0] == "/unblock" and len(parts) > 1:
                    rate_limiter.unblock_ip(parts[1])
                    print(f"{Fore.GREEN}🔓 Unblocked {Fore.YELLOW}{parts[1]}{Style.RESET_ALL}")
                
                elif parts[0] == "/blocked":
                    blocked = rate_limiter.list_blocked()
                    print(f"\n{Fore.RED}🚫 Blocked IPs ({len(blocked)}):{Style.RESET_ALL}")
                    for ip in blocked:
                        print(f"  {Fore.YELLOW}{ip}{Style.RESET_ALL}")
                    print()
                
                elif parts[0] == "/help":
                    print(help_text)
                
                elif parts[0] == "/exit":
                    print(f"\n{Fore.MAGENTA}🌸 Shutting down proxy...{Style.RESET_ALL}")
                    exit(0)
                
                else:
                    print(f"{Fore.RED}❌ Unknown command. Type {Fore.WHITE}/help{Fore.RED} for available commands{Style.RESET_ALL}")

            except Exception as e:
                print(f"{Fore.RED}💥 Command error: {Fore.WHITE}{e}{Style.RESET_ALL}")
