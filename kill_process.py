"""临时脚本：终止指定 PID 的进程（ctypes）"""
import ctypes
import sys

PROCESS_TERMINATE = 0x0001


def kill(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        print(f"PID {pid}: OpenProcess 失败")
        return False
    result = kernel32.TerminateProcess(handle, 1)
    kernel32.CloseHandle(handle)
    print(f"PID {pid}: 终止{'成功' if result else '失败'}")
    return bool(result)


if __name__ == "__main__":
    for pid_str in sys.argv[1:]:
        kill(int(pid_str))
