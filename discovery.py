import socket

def discover_device(timeout=5, retries=3):
    for attempt in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        try:
            sock.sendto(b"FIND_ATTENDANCE_DEVICE", ("255.255.255.255", 8888))
            data, addr = sock.recvfrom(1024)
            response = data.decode('utf-8')
            if response.startswith("ATTENDANCE_DEVICE"):
                parts = response.split(":")
                if len(parts) >= 2:
                    return f"http://{parts[1]}"
        except socket.timeout:
            continue
        finally:
            sock.close()
    return None
