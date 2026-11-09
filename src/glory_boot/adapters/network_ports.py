import socket


def allocate_loopback_port() -> int:
    """向系统申请一个仅绑定本机回环地址的临时 TCP 端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    if not 0 < port <= 65535:
        raise OSError("系统返回了无效的本地端口")
    return port
