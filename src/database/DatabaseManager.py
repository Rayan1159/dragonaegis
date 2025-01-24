import aiomysql
import time

class DatabaseManager:
    def __init__(self, host: str, port: int, user: str, password: str, db: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db = db
        self.pool = None
        
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
        tables = [
            """CREATE TABLE IF NOT EXISTS blocked_ips (
                ip VARCHAR(45) PRIMARY KEY.
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
            )"""
             """CREATE TABLE IF NOT EXISTS servers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ip VARCHAR(45),
                port INT,
                timestamp FLOAT,
                INDEX idx_packets (ip, timestamp)
            )"""
        ]
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                for table in tables:
                    await cur.execute(table)