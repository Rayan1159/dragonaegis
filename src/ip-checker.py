import requests

class IpChecker:
    def __init__(self, ip: str):
        self.ip = ip
        
    def is_vpn(self, ip: str) -> bool:
        pass