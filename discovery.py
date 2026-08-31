import socket
import time

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

def discover_device(timeout=5, retries=3):
    broadcasts = get_broadcast_addresses()
    print(f"[DEBUG] Broadcasting auto-discovery on: {broadcasts}")
    
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
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = data.decode('utf-8')
                    if response.startswith("ATTENDANCE_DEVICE"):
                        parts = response.split(":")
                        if len(parts) >= 2:
                            ip = parts[1].strip()
                            
                            # Verify the HTTP server is actually alive
                            import requests
                            try:
                                res = requests.get(f"http://{ip}/status", timeout=1)
                                if res.status_code == 200:
                                    print(f"[DEBUG] Auto-Discovery found active ESP32 at {ip}!")
                                    return ip
                            except Exception:
                                print(f"[DEBUG] Found device at {ip} but HTTP failed. Ignoring...")
                                continue
                except socket.timeout:
                    break # Stop listening for this attempt
            continue
        finally:
            sock.close()
    
    print("[ERROR] Auto-Discovery failed to find ESP32.")
    return None
