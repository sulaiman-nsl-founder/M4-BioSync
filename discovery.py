import socket

def get_broadcast_addresses():
    broadcasts = ["255.255.255.255"]
    try:
        hostname = socket.gethostname()
        local_ips = socket.gethostbyname_ex(hostname)[2]
        for ip in local_ips:
            parts = ip.split('.')
            if len(parts) == 4:
                parts[3] = '255'
                broadcasts.append('.'.join(parts))
    except Exception:
        pass
    # Add common Hotspot and ESP32 AP subnets
    broadcasts.extend(["192.168.137.255", "192.168.4.255", "192.168.1.255", "192.168.0.255"])
    return list(set(broadcasts))

def discover_device(timeout=3, retries=3):
    broadcasts = get_broadcast_addresses()
    
    for attempt in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        try:
            for bcast in broadcasts:
                try:
                    sock.sendto(b"FIND_ATTENDANCE_DEVICE", (bcast, 8888))
                except Exception:
                    pass
                    
            # Listen for any response
            data, addr = sock.recvfrom(1024)
            response = data.decode('utf-8')
            if response.startswith("ATTENDANCE_DEVICE"):
                parts = response.split(":")
                if len(parts) >= 2:
                    return parts[1].strip()
        except socket.timeout:
            continue
        finally:
            sock.close()
    return None
