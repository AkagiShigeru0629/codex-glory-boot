import socket

from glory_boot.adapters.network_ports import allocate_loopback_port


def test_allocated_port_is_available_on_loopback() -> None:
    port = allocate_loopback_port()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))
