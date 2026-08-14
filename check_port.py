"""端口占用检查：python check_port.py 8003
退出码：0=端口被占用，1=端口空闲
"""
import socket
import sys

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8003
s = socket.socket()
try:
    result = s.connect_ex(("127.0.0.1", port))
finally:
    s.close()
sys.exit(0 if result == 0 else 1)
