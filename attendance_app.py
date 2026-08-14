import customtkinter as ctk
import requests
import threading
import time
from discovery import discover_device
from crypto_utils import decrypt_payload
import socket
from tkinter import filedialog, messagebox
import http.server
import socketserver
import os

# Custom HTTP Request Handler to serve exactly one file for OTA
class FirmwareHandler(http.server.SimpleHTTPRequestHandler):
    firmware_path = ""
    def do_GET(self):
        try:
            with open(self.firmware_path, 'rb') as f:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(os.path.getsize(self.firmware_path)))
                self.end_headers()
                self.wfile.write(f.read())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            
    def log_message(self, format, *args):
        pass # Suppress terminal logs

class AttendanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Smart Attendance System")
        self.geometry("900x650")
        
        self.esp32_ip = None
        self.local_ip = self.get_local_ip()
        self.ota_server = None
        self.ota_port = 8080
        
        # Start local OTA Server
        self.start_ota_server()
        
        # --- UI LAYOUT ---
        # Top Status Bar
        self.status_frame = ctk.CTkFrame(self, height=50)
        self.status_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="Discovering device...", font=("Arial", 16, "bold"), text_color="orange")
        self.status_label.pack(side="left", padx=20, pady=10)
        
        self.settings_btn = ctk.CTkButton(self.status_frame, text="⚙️ OTA Update", fg_color="#4a4a4a", hover_color="#2b2b2b", command=self.trigger_ota_update)
        self.settings_btn.pack(side="right", padx=20, pady=10)
        
        # Main Content
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        # Left Panel - Live Feed
        self.left_panel = ctk.CTkFrame(self.main_frame)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(self.left_panel, text="📋 LIVE FEED", font=("Arial", 18, "bold")).pack(pady=10)
        self.feed_box = ctk.CTkTextbox(self.left_panel, state="disabled")
        self.feed_box.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Right Panel - User Management
        self.right_panel = ctk.CTkFrame(self.main_frame)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(self.right_panel, text="👥 USER MANAGEMENT", font=("Arial", 18, "bold")).pack(pady=10)
        
        # Enrollment Section in Right Panel
        self.enroll_frame = ctk.CTkFrame(self.right_panel)
        self.enroll_frame.pack(pady=10, padx=10, fill="x")
        
        self.id_entry = ctk.CTkEntry(self.enroll_frame, placeholder_text="Enter ID (1-127)")
        self.id_entry.pack(side="left", padx=10, pady=10, expand=True)
        
        self.enroll_btn = ctk.CTkButton(self.enroll_frame, text="+ Enroll", command=self.start_enrollment)
        self.enroll_btn.pack(side="right", padx=10, pady=10)
        
        # Bottom Log Box
        self.log_box = ctk.CTkTextbox(self, height=100)
        self.log_box.pack(fill="x", padx=10, pady=(5, 10))
        self.log("Application started.")

        # --- BACKGROUND TASKS ---
        self.is_running = True
        
        # Start discovery thread
        threading.Thread(target=self.init_discovery, daemon=True).start()

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP
        
    def start_ota_server(self):
        def serve():
            try:
                # Need allow_reuse_address to prevent Address in Use errors if app restarts quickly
                socketserver.TCPServer.allow_reuse_address = True
                self.ota_server = socketserver.TCPServer(("", self.ota_port), FirmwareHandler)
                self.log(f"Local OTA Server running on port {self.ota_port}")
                self.ota_server.serve_forever()
            except Exception as e:
                self.after(0, self.log, f"Local Server error: {e}")
                
        threading.Thread(target=serve, daemon=True).start()

    def trigger_ota_update(self):
        if not self.esp32_ip:
            messagebox.showerror("Error", "ESP32 is not connected!")
            return
            
        file_path = filedialog.askopenfilename(
            title="Select Firmware Update (.bin)",
            filetypes=[("Binary Files", "*.bin")]
        )
        if file_path:
            FirmwareHandler.firmware_path = file_path
            firmware_url = f"http://{self.local_ip}:{self.ota_port}/firmware.bin"
            self.log(f"Hosting firmware at: {firmware_url}")
            self.log("Instructing ESP32 to start OTA update...")
            
            def send_ota():
                try:
                    res = requests.get(f"{self.esp32_ip}/update_firmware?url={firmware_url}", timeout=5)
                    self.after(0, self.log, f"ESP32 OTA Status: {res.text}")
                except Exception as e:
                    self.after(0, self.log, f"OTA Request failed: {e}")
                    
            threading.Thread(target=send_ota, daemon=True).start()

    def log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def log_feed(self, message):
        self.feed_box.configure(state="normal")
        self.feed_box.insert("end", message + "\n")
        self.feed_box.see("end")
        self.feed_box.configure(state="disabled")

    def init_discovery(self):
        self.log("Searching for ESP32 on the network...")
        ip = discover_device(timeout=3, retries=2)
        if ip:
            self.esp32_ip = ip
            self.after(0, self.update_status, f"Connected to {self.esp32_ip}", "green")
            self.log(f"Found device at {self.esp32_ip}")
            threading.Thread(target=self.poll_esp32, daemon=True).start()
        else:
            self.after(0, self.update_status, "Device not found. Please check connection.", "red")
            self.log("Failed to discover ESP32.")

    def update_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def start_enrollment(self):
        user_id = self.id_entry.get()
        if user_id.isdigit() and self.esp32_ip:
            try:
                requests.get(f"{self.esp32_ip}/start_enroll?id={user_id}", timeout=3)
                self.log(f"Started enrollment for ID: {user_id}")
            except Exception as e:
                self.log("Error: Could not reach ESP32.")
        else:
            self.log("Please enter a valid numeric ID and ensure device is connected.")

    def poll_esp32(self):
        while self.is_running:
            if not self.esp32_ip:
                time.sleep(2)
                continue
                
            try:
                status_resp = requests.get(f"{self.esp32_ip}/status", timeout=2)
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    self.after(0, self.update_status, f"Connected to {self.esp32_ip} - {data.get('status', '')}", "green")
                
                poll_resp = requests.get(f"{self.esp32_ip}/poll", timeout=2)
                if poll_resp.status_code == 200:
                    encrypted_b64 = poll_resp.text.strip()
                    if encrypted_b64:
                        event_data = decrypt_payload(encrypted_b64)
                        if event_data and event_data.get("id") != -1:
                            user_id = event_data.get("id")
                            timestamp = event_data.get("timestamp")
                            confidence = event_data.get("confidence")
                            msg = f"User ID {user_id} successfully scanned! (Conf: {confidence}%, Time: {timestamp}ms)"
                            self.after(0, self.log_feed, msg)
                            self.after(0, self.log, msg)

            except requests.exceptions.RequestException:
                self.after(0, self.update_status, "Disconnected from ESP32", "red")
            except Exception as e:
                self.after(0, self.log, f"Poll error: {e}")
            
            time.sleep(1)

if __name__ == "__main__":
    app = AttendanceApp()
    app.mainloop()