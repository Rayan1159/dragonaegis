import aiomysql
import time

class DatabaseManager:
    def __init__(self, host: str, port: int, user: str, password: str, db: str, server_password: str, refresh_tables: bool = False):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db = db
        self.pool = None
        self.refresh_tables = refresh_tables    
        self.server_password = server_password
        
    async def initialize(self):
        self.pool = await aiomysql.create_pool(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.db,
            autocommit=True,
            pool_recycle=300
        )
        await self._create_tables()
        
    async def _create_tables(self):
        if self.refresh_tables:
            tables = [
                """CREATE TABLE IF NOT EXISTS blocked_ips (
                    ip VARCHAR(45) PRIMARY KEY,
                    server_id INT
                )""",
                """CREATE TABLE IF NOT EXISTS connections (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    ip VARCHAR(45),
                    server_id INT,
                    timestamp FLOAT,
                    INDEX idx_conn (ip, timestamp)
                )""",
                """CREATE TABLE IF NOT EXISTS packets (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    ip VARCHAR(45),
                    server_id INT,
                    timestamp FLOAT,
                    INDEX idx_packets (ip, timestamp)
                )""",
                """CREATE TABLE IF NOT EXISTS servers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    ip VARCHAR(45),
                    port INT,
                    timestamp FLOAT,
                    handshakes INT,
                    password VARCHAR(35)
                    INDEX idx_server (ip, timestamp)
                )"""
            ]
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    for table in tables:
                        await cur.execute(table)
        else:
            print("Skipping table creation, refresh_tables is False")
                    
    async def block_ip(self, ip: str, server_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO blocked_ips (ip, server_id) VALUES (%s, %s)", (ip, server_id))
                
    async def unblock_ip(self, ip: str, server_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM blocked_ips WHERE ip = %s AND server_id = %s", (ip, server_id))
                
    async def list_blocked(self, server_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT ip FROM blocked_ips WHERE server_id = %s", (server_id,))
                return [row[0] async for row in cur]
    
    async def log_connection(self, ip: str, server_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO connections (ip, server_id, timestamp) VALUES (%s, %s, %s)", (ip, server_id, time.time()))
                
    async def log_packet(self, ip: str, server_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO packets (ip, server_id, timestamp) VALUES (%s, %s, %s)", (ip, server_id, time.time()))
                
    async def get_connection_count(self, address: str, id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM connections WHERE ip = %s AND server_id = %s", (address, id))
                return (await cur.fetchone())[0]
            
    async def get_packet_count(self, ip: str, server_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM packets WHERE ip = %s AND server_id = %s", (ip, server_id))
                return (await cur.fetchone())[0]
    
    async def get_server_id(self, ip: str, port: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id FROM servers WHERE ip = %s AND port = %s", (ip, port))
                return (await cur.fetchone())[0]
            
    async def log_server(self, ip: str, port: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO servers (ip, port, timestamp) VALUES (%s, %s, %s)", (ip, port, time.time()))
            
    async def cleanup_old_entries(self):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Keep 1 hour of data for demonstration, adjust as needed
                await cur.execute(
                    "DELETE FROM connections WHERE timestamp < %s",
                    (time.time() - 3600,)
                )
                await cur.execute(
                    "DELETE FROM packets WHERE timestamp < %s",
                    (time.time() - 3600,)
                )
                
    async def get_server_password(self, ip, port, id):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT password FROM servers WHERE ip = % AND port = % AND id = %",
                    (ip, port, id)
                )
                return (await cur.fetchone())[0]

    async def increment_handshakes(self, ip: str, port: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE servers SET handshakes = handshakes + 1 WHERE ip = %s AND port = %s",
                    (ip, port)
                )