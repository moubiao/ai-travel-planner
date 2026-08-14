"""临时脚本：查找占用指定端口的进程"""
import sys

import psutil

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8003
found = False
for conn in psutil.net_connections():
    if conn.laddr and conn.laddr.port == port:
        found = True
        try:
            proc = psutil.Process(conn.pid)
            print(f"端口 {port}: PID {conn.pid} | {proc.name()} | {conn.status}")
            print(f"  命令行: {' '.join(proc.cmdline())[:150]}")
        except Exception as e:
            print(f"端口 {port}: PID {conn.pid} | 进程信息不可用: {e}")
if not found:
    print(f"端口 {port}: 无占用进程")
