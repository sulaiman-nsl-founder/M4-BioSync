import customtkinter as ctk
import requests
import threading
import time
from discovery import discover_device
from crypto_utils import decrypt_payload
from auth import AuthWindow
import socket
from tkinter import filedialog, messagebox, ttk
import http.server
import socketserver
import os
from datetime import datetime
from data_manager import DataManager
from sheets_sync import SheetsSync

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

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
        except Exception:
            self.send_response(500)
            self.end_headers()
            
    def log_message(self, format, *args): pass # Suppress terminal logs

class EnrollmentModal(ctk.CTkToplevel):
    def __init__(self, master_app):
        super().__init__(master_app)
        self.title("Enroll Employee")
        self.geometry("450x400")
        self.attributes("-topmost", True)
        self.master_app = master_app
        self.db = master_app.db
        
        self.step = 1
        self.target_finger_id = self.db.get_next_finger_id()
        
        # UI Elements
        self.title_lbl = ctk.CTkLabel(self, text="Step 1: Employee Details", font=("Arial", 18, "bold"))
        self.title_lbl.pack(pady=20)
        
        # Pause background polling to prevent overwhelming the ESP32
        self.master_app._pause_polling = True
        
        self.form_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.form_frame.pack(fill="both", expand=True, padx=30)
        
        self.emp_id = ctk.CTkEntry(self.form_frame, placeholder_text="Employee ID (e.g. EMP-001)")
        self.emp_id.pack(fill="x", pady=5)
        
        self.name = ctk.CTkEntry(self.form_frame, placeholder_text="Full Name")
        self.name.pack(fill="x", pady=5)
        
        self.dept = ctk.CTkEntry(self.form_frame, placeholder_text="Department")
        self.dept.pack(fill="x", pady=5)
        
        self.desig = ctk.CTkEntry(self.form_frame, placeholder_text="Designation")
        self.desig.pack(fill="x", pady=5)
        
        self.status_lbl = ctk.CTkLabel(self, text="", font=("Arial", 14), text_color="orange")
        self.status_lbl.pack(pady=10)
        
        self.next_btn = ctk.CTkButton(self, text="Next Step →", command=self.next_step)
        self.next_btn.pack(pady=20)
        
        self.enroll_active = False

    def next_step(self):
        if self.step == 1:
            if not all([self.emp_id.get(), self.name.get(), self.dept.get(), self.desig.get()]):
                messagebox.showerror("Error", "All fields are required", parent=self)
                return
            
            if not self.master_app.esp32_ip:
                messagebox.showerror("Error", "ESP32 is not connected!", parent=self)
                return
            
            self.step = 2
            self.form_frame.pack_forget()
            self.title_lbl.configure(text=f"Step 2: Fingerprint Scan (ID {self.target_finger_id})")
            self.status_lbl.configure(text="Connecting to ESP32...")
            self.next_btn.configure(state="disabled")
            
            # Start ESP32 Enrollment
            threading.Thread(target=self.start_esp32_enrollment, daemon=True).start()
            
    def start_esp32_enrollment(self):
        try:
            res = requests.get(f"http://{self.master_app.esp32_ip}/start_enroll?id={self.target_finger_id}", timeout=5)
            if res.status_code == 200:
                self.enroll_active = True
                self.poll_enrollment_status()
            else:
                self.after(0, lambda: self.status_lbl.configure(text="Failed to start on ESP32", text_color="red"))
        except Exception:
            self.after(0, lambda: self.status_lbl.configure(text="ESP32 Unreachable", text_color="red"))

    def poll_enrollment_status(self):
        if not self.enroll_active: return
        try:
            res = requests.get(f"http://{self.master_app.esp32_ip}/status", timeout=2)
            if res.status_code == 200:
                data = res.json()
                status = data.get("status", "")
                
                # Filter out default idle status so we only show enrollment steps
                if "Idle" not in status:
                    self.after(0, lambda: self.status_lbl.configure(text=status))
                
                if "Success!" in status:
                    self.enroll_active = False
                    self.save_employee()
                    self.after(0, lambda: self.status_lbl.configure(text="✅ Successfully Enrolled!", text_color="green"))
                    self.after(0, lambda: self.next_btn.configure(text="Finish", state="normal", command=self.finish))
                    return
                elif "Error" in status:
                    self.enroll_active = False
                    self.after(0, lambda: self.status_lbl.configure(text=f"❌ {status} (Click Restart)", text_color="red"))
                    self.after(0, lambda: self.next_btn.configure(text="Restart Enrollment", state="normal", command=self.restart_enrollment))
                    return
                elif any(word in status for word in ["Scanned ID", "Cooldown", "Offline"]):
                    self.enroll_active = False
                    self.after(0, lambda: self.status_lbl.configure(text="❌ Enrollment dropped (Prints didn't match). Click Restart.", text_color="red"))
                    self.after(0, lambda: self.next_btn.configure(text="Restart Enrollment", state="normal", command=self.restart_enrollment))
                    return
        except Exception:
            pass
            
        if self.enroll_active:
            self.after(1000, self.poll_enrollment_status)

    def restart_enrollment(self):
        self.next_btn.configure(state="disabled")
        self.status_lbl.configure(text="Restarting...", text_color="orange")
        threading.Thread(target=self.start_esp32_enrollment, daemon=True).start()

    def save_employee(self):
        self.db.add_employee(
            self.emp_id.get(), 
            self.name.get(), 
            self.dept.get(), 
            self.desig.get(), 
            self.target_finger_id
        )
        self.after(0, self.master_app.load_employee_table)

    def finish(self):
        self.master_app._pause_polling = False
        self.destroy()
        
    def destroy(self):
        self.master_app._pause_polling = False
        super().destroy()

class AttendanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("M4 BioSync - Enterprise")
        self.geometry("1100x700")
        
        # Hide main window initially for PIN prompt
        self.withdraw()
        
        # Initialize Data Manager
        self.db = DataManager()
        self.cloud_sync = SheetsSync()
        
        # Start Auth Window (Blocks UI until success)
        self.auth_window = AuthWindow(self, self.on_auth_success)
        
        self.esp32_ip = None
        self.local_ip = self.get_local_ip()
        self.ota_server = None
        self.ota_port = 8080
        self.is_running = True
        self._pause_polling = False
        
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
        
    def on_auth_success(self):
        self.deiconify() # Show main window
        self.setup_ui()
        self.start_ota_server()
        threading.Thread(target=self.init_discovery, daemon=True).start()

    def setup_ui(self):
        # Configure grid for sidebar layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # --- SIDEBAR ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1)
        
        ctk.CTkLabel(self.sidebar_frame, text="🔷 M4 BioSync", font=("Arial", 22, "bold")).grid(row=0, column=0, padx=20, pady=(20, 30))
        
        self.btn_dash = ctk.CTkButton(self.sidebar_frame, text="📊 Dashboard", anchor="w", command=lambda: self.select_frame("Dashboard"))
        self.btn_dash.grid(row=1, column=0, padx=20, pady=10)
        
        self.btn_att = ctk.CTkButton(self.sidebar_frame, text="🕐 Attendance", anchor="w", command=lambda: self.select_frame("Attendance"))
        self.btn_att.grid(row=2, column=0, padx=20, pady=10)
        
        self.btn_emp = ctk.CTkButton(self.sidebar_frame, text="👥 Employees", anchor="w", command=lambda: self.select_frame("Employees"))
        self.btn_emp.grid(row=3, column=0, padx=20, pady=10)
        
        self.btn_rep = ctk.CTkButton(self.sidebar_frame, text="📄 Reports", anchor="w", command=lambda: self.select_frame("Reports"))
        self.btn_rep.grid(row=4, column=0, padx=20, pady=10)
        
        self.btn_set = ctk.CTkButton(self.sidebar_frame, text="⚙️ Settings", anchor="w", command=lambda: self.select_frame("Settings"))
        self.btn_set.grid(row=5, column=0, padx=20, pady=10)
        
        # --- MAIN CONTENT AREA ---
        self.main_content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_content.grid(row=0, column=1, sticky="nsew")
        self.main_content.grid_rowconfigure(1, weight=1)
        self.main_content.grid_columnconfigure(0, weight=1)
        
        # --- DEVICE STATUS BAR (Top) ---
        self.top_bar = ctk.CTkFrame(self.main_content, height=50, corner_radius=10)
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=20, pady=15)
        
        self.conn_dot = ctk.CTkLabel(self.top_bar, text="🔴", font=("Arial", 16))
        self.conn_dot.pack(side="left", padx=(15, 5), pady=10)
        
        self.status_label = ctk.CTkLabel(self.top_bar, text="Device: Disconnected", font=("Arial", 14, "bold"))
        self.status_label.pack(side="left", padx=5, pady=10)
        
        self.rtc_label = ctk.CTkLabel(self.top_bar, text="RTC: --:--:--", font=("Arial", 14))
        self.rtc_label.pack(side="right", padx=20, pady=10)
        
        self.rssi_label = ctk.CTkLabel(self.top_bar, text="RSSI: -- dBm", font=("Arial", 14))
        self.rssi_label.pack(side="right", padx=10, pady=10)
        
        # --- FRAMES DICTIONARY ---
        self.frames = {}
        
        # 1. DASHBOARD FRAME
        dash_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.frames["Dashboard"] = dash_frame
        
        # Stats Cards
        stats_frame = ctk.CTkFrame(dash_frame, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=10)
        
        card1 = ctk.CTkFrame(stats_frame, corner_radius=10)
        card1.pack(side="left", fill="both", expand=True, padx=5)
        ctk.CTkLabel(card1, text="Total Present", font=("Arial", 14)).pack(pady=(15, 5))
        ctk.CTkLabel(card1, text="0", font=("Arial", 28, "bold"), text_color="#00FF00").pack(pady=(0, 15))
        
        card2 = ctk.CTkFrame(stats_frame, corner_radius=10)
        card2.pack(side="left", fill="both", expand=True, padx=5)
        ctk.CTkLabel(card2, text="Total Absent", font=("Arial", 14)).pack(pady=(15, 5))
        ctk.CTkLabel(card2, text="0", font=("Arial", 28, "bold"), text_color="#FF4444").pack(pady=(0, 15))
        
        card3 = ctk.CTkFrame(stats_frame, corner_radius=10)
        card3.pack(side="left", fill="both", expand=True, padx=5)
        ctk.CTkLabel(card3, text="Total Late", font=("Arial", 14)).pack(pady=(15, 5))
        ctk.CTkLabel(card3, text="0", font=("Arial", 28, "bold"), text_color="#FFDD00").pack(pady=(0, 15))
        
        # Recent Scans Feed
        ctk.CTkLabel(dash_frame, text="Recent Scans", font=("Arial", 18, "bold")).pack(anchor="w", padx=20, pady=(20, 10))
        self.feed_box = ctk.CTkTextbox(dash_frame, state="disabled", font=("Courier", 14))
        self.feed_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # 2. SETTINGS FRAME (OTA & Wi-Fi)
        set_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.frames["Settings"] = set_frame
        
        ctk.CTkLabel(set_frame, text="Device Settings & OTA", font=("Arial", 18, "bold")).pack(anchor="w", padx=20, pady=20)
        
        ota_panel = ctk.CTkFrame(set_frame, corner_radius=10)
        ota_panel.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(ota_panel, text="Firmware Over-The-Air Update", font=("Arial", 16, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(ota_panel, text="Select a compiled .bin file to upload to the ESP32 wirelessly.").pack(anchor="w", padx=20, pady=(0, 15))
        ctk.CTkButton(ota_panel, text="Select Firmware & Update", command=self.trigger_ota_update, width=200).pack(anchor="w", padx=20, pady=(0, 20))
        
        wifi_panel = ctk.CTkFrame(set_frame, corner_radius=10)
        wifi_panel.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(wifi_panel, text="Wi-Fi Configuration (AP Setup Mode)", font=("Arial", 16, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(wifi_panel, text="Connect this PC to the 'BioSync_Setup' Wi-Fi network, then enter your router details.").pack(anchor="w", padx=20, pady=(0, 15))
        
        self.ssid_entry = ctk.CTkEntry(wifi_panel, placeholder_text="Wi-Fi SSID", width=250)
        self.ssid_entry.pack(anchor="w", padx=20, pady=5)
        self.pass_entry = ctk.CTkEntry(wifi_panel, placeholder_text="Wi-Fi Password", show="*", width=250)
        self.pass_entry.pack(anchor="w", padx=20, pady=5)
        ctk.CTkButton(wifi_panel, text="Send Wi-Fi Credentials", command=self.provision_wifi, width=200).pack(anchor="w", padx=20, pady=(10, 20))
        
        ip_panel = ctk.CTkFrame(set_frame, corner_radius=10)
        ip_panel.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(ip_panel, text="Manual Device Connection", font=("Arial", 16, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(ip_panel, text="If auto-discovery fails, enter the pure IP from the Serial Monitor (e.g. 192.168.137.122).").pack(anchor="w", padx=20, pady=(0, 15))
        
        self.ip_entry = ctk.CTkEntry(ip_panel, placeholder_text="Device IP Address", width=250)
        self.ip_entry.pack(anchor="w", padx=20, pady=5)
        ctk.CTkButton(ip_panel, text="Connect to IP", command=self.manual_connect, width=200).pack(anchor="w", padx=20, pady=(10, 20))

        # PIN Change Panel
        pin_panel = ctk.CTkFrame(set_frame, corner_radius=10)
        pin_panel.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(pin_panel, text="Security Settings", font=("Arial", 16, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(pin_panel, text="Change the Admin PIN used to log into this software.").pack(anchor="w", padx=20, pady=(0, 15))
        
        self.new_pin_entry = ctk.CTkEntry(pin_panel, placeholder_text="Enter New PIN", show="*", width=250)
        self.new_pin_entry.pack(anchor="w", padx=20, pady=5)
        ctk.CTkButton(pin_panel, text="Change PIN", command=self.change_admin_pin, width=200).pack(anchor="w", padx=20, pady=(10, 20))

        # Hardware Maintenance Panel
        hw_panel = ctk.CTkFrame(set_frame, corner_radius=10)
        hw_panel.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(hw_panel, text="Hardware Maintenance", font=("Arial", 16, "bold"), text_color="orange").pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(hw_panel, text="Use this to permanently wipe the ESP32 sensor memory if you get duplicate finger IDs.").pack(anchor="w", padx=20, pady=(0, 15))
        ctk.CTkButton(hw_panel, text="Format Fingerprint Sensor", fg_color="red", hover_color="#8B0000", command=self.format_sensor_memory, width=250).pack(anchor="w", padx=20, pady=(10, 20))

        
        # 3. EMPLOYEES FRAME
        emp_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.frames["Employees"] = emp_frame
        
        emp_top = ctk.CTkFrame(emp_frame, fg_color="transparent")
        emp_top.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(emp_top, text="Employee Management", font=("Arial", 20, "bold")).pack(side="left")
        ctk.CTkButton(emp_top, text="+ Enroll New Employee", command=self.open_enrollment_wizard).pack(side="right")
        
        search_bar = ctk.CTkEntry(emp_top, placeholder_text="Search by name or ID...", width=250)
        search_bar.pack(side="right", padx=20)
        search_bar.bind("<KeyRelease>", self.filter_employees)
        self.emp_search_bar = search_bar
        
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2b2b2b", foreground="white", fieldbackground="#2b2b2b", rowheight=30, borderwidth=0)
        style.map('Treeview', background=[('selected', '#1f538d')])
        
        self.emp_tree = ttk.Treeview(emp_frame, columns=("ID", "Name", "Department", "Designation", "Finger ID", "Status"), show="headings")
        self.emp_tree.heading("ID", text="Emp ID")
        self.emp_tree.heading("Name", text="Full Name")
        self.emp_tree.heading("Department", text="Department")
        self.emp_tree.heading("Designation", text="Designation")
        self.emp_tree.heading("Finger ID", text="Finger ID")
        self.emp_tree.heading("Status", text="Status")
        
        self.emp_tree.column("ID", width=100)
        self.emp_tree.column("Name", width=200)
        self.emp_tree.column("Finger ID", width=80)
        self.emp_tree.column("Status", width=100)
        self.emp_tree.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Action Buttons below Treeview
        emp_bot = ctk.CTkFrame(emp_frame, fg_color="transparent")
        emp_bot.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(emp_bot, text="🗑 Delete Selected", fg_color="red", hover_color="#8B0000", command=self.delete_employee).pack(side="right")
        
        self.load_employee_table()
        # 4. ATTENDANCE LOG FRAME (Phase 5)
        att_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.frames["Attendance"] = att_frame
        
        ctk.CTkLabel(att_frame, text="Real-Time Attendance Log", font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=20)
        
        self.att_tree = ttk.Treeview(att_frame, columns=("Date", "Time", "Emp ID", "Name", "Dept", "Type", "Status", "Hours"), show="headings")
        self.att_tree.heading("Date", text="Date")
        self.att_tree.heading("Time", text="Time")
        self.att_tree.heading("Emp ID", text="Emp ID")
        self.att_tree.heading("Name", text="Full Name")
        self.att_tree.heading("Dept", text="Department")
        self.att_tree.heading("Type", text="Punch Type")
        self.att_tree.heading("Status", text="Status")
        self.att_tree.heading("Hours", text="Hours")
        
        self.att_tree.column("Date", width=100)
        self.att_tree.column("Time", width=100)
        self.att_tree.column("Emp ID", width=80)
        self.att_tree.column("Name", width=150)
        self.att_tree.column("Type", width=100)
        self.att_tree.column("Hours", width=80)
        self.att_tree.column("Status", width=100)
        self.att_tree.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        ctk.CTkButton(att_frame, text="🔄 Refresh Log", command=self.load_attendance_table).pack(anchor="e", padx=20, pady=10)
        self.load_attendance_table()
        
        # 5. REPORTS & CLOUD FRAME (Phase 5)
        rep_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.frames["Reports"] = rep_frame
        
        ctk.CTkLabel(rep_frame, text="Data Export & Cloud Sync", font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=20)
        
        export_panel = ctk.CTkFrame(rep_frame, corner_radius=10)
        export_panel.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(export_panel, text="Export Local Data", font=("Arial", 16, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(export_panel, text="Export the raw attendance logs to an Excel or CSV file for payroll processing.").pack(anchor="w", padx=20, pady=(0, 15))
        ctk.CTkButton(export_panel, text="Export to CSV", command=self.export_csv, width=200).pack(anchor="w", padx=20, pady=(10, 20))
        
        cloud_panel = ctk.CTkFrame(rep_frame, corner_radius=10)
        cloud_panel.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(cloud_panel, text="Google Sheets Integration", font=("Arial", 16, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        
        if hasattr(self, 'cloud_sync') and self.cloud_sync.is_configured:
            ctk.CTkLabel(cloud_panel, text="Status: Active & Connected to 'BioSync_Attendance_Log'", text_color="green").pack(anchor="w", padx=20, pady=(0, 15))
            ctk.CTkButton(cloud_panel, text="Force Cloud Sync", state="normal", width=200).pack(anchor="w", padx=20, pady=(10, 20))
        else:
            ctk.CTkLabel(cloud_panel, text="Status: Not Configured (Missing credentials.json)", text_color="orange").pack(anchor="w", padx=20, pady=(0, 15))
            ctk.CTkButton(cloud_panel, text="Force Cloud Sync", state="disabled", width=200).pack(anchor="w", padx=20, pady=(10, 20))
        
        # Default view
        self.select_frame("Dashboard")

    def load_employee_table(self, search_query=""):
        # Clear existing
        for row in self.emp_tree.get_children():
            self.emp_tree.delete(row)
            
        df = self.db.load_employees()
        if search_query:
            df = df[df["full_name"].str.contains(search_query, case=False, na=False) | 
                    df["emp_id"].str.contains(search_query, case=False, na=False)]
            
        for _, row in df.iterrows():
            self.emp_tree.insert("", "end", values=(
                row["emp_id"], row["full_name"], row["department"], 
                row["designation"], row["finger_id"], row["status"]
            ))

    def filter_employees(self, event):
        query = self.emp_search_bar.get()
        self.load_employee_table(query)

    def delete_employee(self):
        selected = self.emp_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an employee to delete")
            return
            
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to permanently delete this employee?"):
            for item in selected:
                values = self.emp_tree.item(item, "values")
                emp_id = values[0]
                
                # Fetch employee data to get finger ID
                df = self.db.load_employees()
                match = df[df["emp_id"] == str(emp_id)]
                if not match.empty:
                    emp_data = match.iloc[0].to_dict()
                    # Delete from hardware if connected
                    finger_id_val = emp_data.get('finger_id')
                    if finger_id_val is not None and str(finger_id_val).strip() != "" and str(finger_id_val) != "nan" and getattr(self, 'esp32_ip', None):
                        try:
                            finger_id = int(float(finger_id_val)) # Handle float strings from pandas
                            del_res = requests.get(f"http://{self.esp32_ip}/delete_finger?id={finger_id}", timeout=5)
                            if del_res.status_code != 200:
                                print(f"[DEBUG] Hardware delete warning: {del_res.text}")
                        except Exception as e:
                            print(f"[DEBUG] Hardware delete error: {e}")

                self.db.hard_delete_employee(emp_id)
            self.load_employee_table()

    def load_attendance_table(self):
        for row in self.att_tree.get_children():
            self.att_tree.delete(row)
            
        try:
            df = self.db.load_attendance()
            # Sort chronologically first to calculate hours
            df = df.sort_values(by=["date", "time"], ascending=[True, True])
            
            # Calculate hours
            display_data = []
            check_ins = {}
            for _, row in df.iterrows():
                hours_str = "--"
                emp_id = row["emp_id"]
                if row["punch_type"] == "Check-In":
                    check_ins[emp_id] = datetime.strptime(f'{row["date"]} {row["time"]}', "%Y-%m-%d %H:%M:%S")
                elif row["punch_type"] == "Check-Out" and emp_id in check_ins:
                    checkout_time = datetime.strptime(f'{row["date"]} {row["time"]}', "%Y-%m-%d %H:%M:%S")
                    diff = checkout_time - check_ins[emp_id]
                    hours = diff.total_seconds() / 3600.0
                    hours_str = f"{hours:.2f} hrs"
                    del check_ins[emp_id] # Reset
                    
                display_data.append((
                    row["date"], row["time"], row["emp_id"], 
                    row["full_name"], row["department"], 
                    row["punch_type"], row["status"], hours_str
                ))
                
            # Reverse display_data to show most recent first
            display_data.reverse()
            
            for row in display_data:
                self.att_tree.insert("", "end", values=row)
        except Exception as e:
            print(f"[ERROR] Failed to load attendance table: {e}")

    def export_csv(self):
        import shutil
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")], title="Export Attendance Logs")
        if save_path:
            try:
                shutil.copy("attendance.csv", save_path)
                messagebox.showinfo("Success", f"Attendance logs exported successfully to:\n{save_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export CSV: {e}")

    def open_enrollment_wizard(self):
        EnrollmentModal(self)
        
    def select_frame(self, name):
        # Hide all frames
        for f in self.frames.values():
            f.grid_forget()
        # Show selected
        if name in self.frames:
            self.frames[name].grid(row=1, column=0, sticky="nsew")

    def start_ota_server(self):
        def serve():
            try:
                socketserver.TCPServer.allow_reuse_address = True
                self.ota_server = socketserver.TCPServer(("", self.ota_port), FirmwareHandler)
                self.ota_server.serve_forever()
            except Exception:
                pass
        threading.Thread(target=serve, daemon=True).start()

    def trigger_ota_update(self):
        if not self.esp32_ip:
            messagebox.showerror("Error", "ESP32 is not connected!")
            return
            
        file_path = filedialog.askopenfilename(title="Select Firmware Update (.bin)", filetypes=[("Binary Files", "*.bin")])
        if file_path:
            FirmwareHandler.firmware_path = file_path
            firmware_url = f"http://{self.local_ip}:{self.ota_port}/firmware.bin"
            
            def send_ota():
                try:
                    requests.get(f"http://{self.esp32_ip}/update_firmware?url={firmware_url}", timeout=5)
                except Exception:
                    pass
            threading.Thread(target=send_ota, daemon=True).start()
            messagebox.showinfo("OTA Update", "OTA Update initiated! Check device LEDs.")

    def provision_wifi(self):
        ssid = self.ssid_entry.get()
        pwd = self.pass_entry.get()
        if not ssid:
            messagebox.showerror("Error", "SSID cannot be empty")
            return
            
        def send_req():
            try:
                res = requests.get(f"http://192.168.4.1/set_wifi?ssid={ssid}&pass={pwd}", timeout=5)
                if res.status_code == 200:
                    self.after(0, messagebox.showinfo, "Success", "Credentials sent! ESP32 is rebooting.")
                else:
                    self.after(0, messagebox.showerror, "Error", "Failed to set credentials.")
            except Exception as e:
                self.after(0, messagebox.showerror, "Error", f"Could not reach device. Are you connected to 'BioSync_Setup'?\n{e}")
                
        threading.Thread(target=send_req, daemon=True).start()

    def manual_connect(self):
        ip = self.ip_entry.get().strip()
        # Clean up all possible prefixes and suffixes
        ip = ip.replace("https://", "").replace("http://", "").replace("http//", "")
        ip = ip.split("/")[0] # Remove any trailing paths if they pasted a URL
        
        print(f"[DEBUG] Manual connection requested for IP: {ip}")
        if not ip:
            messagebox.showerror("Error", "Please enter an IP address")
            return
        self._manual_override = True
        self.esp32_ip = ip
        self.update_top_bar(f"Device: ESP32 @ {self.esp32_ip}", "🟢")
        self.log_feed(f"Manual connection overridden to {ip}")
        print(f"[DEBUG] Triggering offline sync for {ip}...")
        threading.Thread(target=self._sync_hardware_clock, daemon=True).start()
        threading.Thread(target=self.sync_offline_data, daemon=True).start()
        # Start poll loop if not already polling
        if not getattr(self, '_is_polling', False):
            print("[DEBUG] Starting background polling thread...")
            threading.Thread(target=self.poll_esp32, daemon=True).start()

    def format_sensor_memory(self):
        if not self.esp32_ip:
            messagebox.showerror("Error", "ESP32 is not connected!")
            return
            
        if messagebox.askyesno("DANGER", "Are you absolutely sure you want to WIPE the ESP32 hardware memory?\n\nThis will instantly delete ALL registered fingerprints. Employee data will remain in Python, but you will have to re-enroll every single person's finger!"):
            try:
                res = requests.get(f"http://{self.esp32_ip}/clear_sensor", timeout=10)
                if res.status_code == 200:
                    messagebox.showinfo("Success", "Sensor memory wiped completely. Please re-enroll all employees.")
                else:
                    messagebox.showerror("Error", f"Failed to wipe sensor: {res.text}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not reach device to wipe memory: {e}")

    def change_admin_pin(self):
        new_pin = self.new_pin_entry.get().strip()
        if not new_pin or len(new_pin) < 4:
            messagebox.showerror("Error", "PIN must be at least 4 characters long.")
            return
            
        import configparser
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
        if os.path.exists(config_path):
            config.read(config_path)
            
        if 'Security' not in config:
            config['Security'] = {}
            
        config['Security']['ADMIN_PIN'] = new_pin
        with open(config_path, 'w') as f:
            config.write(f)
            
        messagebox.showinfo("Success", "Admin PIN updated successfully! It will take effect on next launch.")
        self.new_pin_entry.delete(0, 'end')

    def log_feed(self, message):
        self.feed_box.configure(state="normal")
        self.feed_box.insert("1.0", message + "\n") # Insert at the top of the list
        self.feed_box.configure(state="disabled")

    def _sync_hardware_clock(self):
        try:
            now = datetime.now()
            url = f"http://{self.esp32_ip}/sync_time?y={now.year}&m={now.month}&d={now.day}&h={now.hour}&min={now.minute}&s={now.second}"
            requests.get(url, timeout=3)
            print("[DEBUG] ESP32 RTC synchronized with PC time.")
        except Exception as e:
            print(f"[DEBUG] Failed to sync RTC: {e}")

    def init_discovery(self):
        if getattr(self, '_manual_override', False):
            return
            
        ip = discover_device(timeout=3, retries=2)
        if ip:
            if getattr(self, '_manual_override', False): return
            self.esp32_ip = ip
            self.after(0, self.update_top_bar, f"Device: ESP32 @ {self.esp32_ip}", "🟢")
            
            # Synchronize the hardware RTC time
            threading.Thread(target=self._sync_hardware_clock, daemon=True).start()
            
            # Immediately trigger offline sync on connection
            threading.Thread(target=self.sync_offline_data, daemon=True).start()
            
            # Start background polling
            if not getattr(self, '_is_polling', False):
                threading.Thread(target=self.poll_esp32, daemon=True).start()
        else:
            if getattr(self, '_manual_override', False): return
            self.after(0, self.update_top_bar, "Device: Disconnected (Retrying...)", "🔴")
            time.sleep(3)
            self.init_discovery() # Keep trying in background loop

    def update_top_bar(self, text, dot, rssi="--", rtc="--:--:--"):
        self.status_label.configure(text=text)
        self.conn_dot.configure(text=dot)
        self.rssi_label.configure(text=f"RSSI: {rssi} dBm")
        self.rtc_label.configure(text=f"RTC: {rtc}")

    def sync_offline_data(self):
        try:
            res = requests.get(f"http://{self.esp32_ip}/sync_offline", timeout=5)
            if res.status_code == 200 and res.text.strip():
                lines = res.text.strip().split('\n')
                for line in lines:
                    event = decrypt_payload(line.strip())
                    if event:
                        uid = event.get('id')
                        timestamp = event.get('timestamp', "").replace("T", " ")
                        
                        # Lookup Employee Name
                        emp = self.db.get_employee_by_finger_id(uid)
                        if emp:
                            # Split timestamp into date and time
                            date_part = timestamp.split(" ")[0] if " " in timestamp else datetime.now().strftime("%Y-%m-%d")
                            
                            today_logs = self.db.load_attendance()
                            emp_today = today_logs[(today_logs["emp_id"] == emp["emp_id"]) & (today_logs["date"] == date_part)]
                            
                            if len(emp_today) % 2 == 0:
                                punch_type = "Check-In"
                                status = "On-Time"
                                icon = "🟢"
                            else:
                                punch_type = "Check-Out"
                                status = "Completed"
                                icon = "🔵"
                                
                            # Save to CSV Database
                            new_punch = self.db.log_punch(emp["emp_id"], emp["full_name"], emp["department"], punch_type, status, confidence=98, override_datetime=timestamp)
                            
                            # Phase 5: Cloud Sync
                            punch_data = [
                                new_punch["date"], new_punch["time"], new_punch["emp_id"], 
                                new_punch["full_name"], new_punch["department"], 
                                new_punch["punch_type"], new_punch["status"], new_punch["confidence"]
                            ]
                            self.cloud_sync.sync_punch_async(punch_data)
                            
                            self.after(0, self.log_feed, f"[{timestamp}] [OFFLINE] {emp['full_name']} | {icon} {punch_type} ({status})")
                        else:
                            self.after(0, self.log_feed, f"[{timestamp}] [OFFLINE] Unknown ID {uid} | 🔴 Unregistered")
                
                # Refresh table to show new offline syncs
                self.after(0, self.load_attendance_table)
        except Exception as e:
            print(f"[DEBUG] Offline sync failed: {e}")

    def poll_esp32(self):
        self._is_polling = True
        print("[DEBUG] Polling thread started.")
        fail_count = 0
        while self.is_running:
            if getattr(self, '_pause_polling', False):
                time.sleep(1)
                continue
                
            try:
                # 1. Update Status Bar
                status_url = f"http://{self.esp32_ip}/status"
                status_resp = requests.get(status_url, timeout=3)
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    rssi = data.get('rssi', '--')
                    rtc_time = data.get('time', '--:--:--').split('T')[-1]
                    self.after(0, self.update_top_bar, f"Device: Connected @ {self.esp32_ip}", "🟢", rssi, rtc_time)
                    fail_count = 0 # Reset fail count on success
                else:
                    print(f"[DEBUG] Status endpoint returned: {status_resp.status_code}")
                
                # 2. Check for new punches
                poll_url = f"http://{self.esp32_ip}/poll"
                poll_resp = requests.get(poll_url, timeout=3)
                if poll_resp.status_code == 200:
                    encrypted_b64 = poll_resp.text.strip()
                    if encrypted_b64:
                        event_data = decrypt_payload(encrypted_b64)
                        if event_data and event_data.get("id") != -1:
                            uid = event_data.get("id")
                            timestamp = event_data.get("timestamp", "").replace("T", " ")
                            
                            # Lookup Employee Name
                            emp = self.db.get_employee_by_finger_id(uid)
                            if emp:
                                today_logs = self.db.load_attendance()
                                emp_today = today_logs[(today_logs["emp_id"] == emp["emp_id"]) & (today_logs["date"] == datetime.now().strftime("%Y-%m-%d"))]
                                
                                if len(emp_today) % 2 == 0:
                                    punch_type = "Check-In"
                                    status = "On-Time"
                                    icon = "🟢"
                                else:
                                    punch_type = "Check-Out"
                                    status = "Completed"
                                    icon = "🔵"
                                    
                                # Save to CSV Database
                                new_punch = self.db.log_punch(emp["emp_id"], emp["full_name"], emp["department"], punch_type, status, confidence=98)
                                
                                # Phase 5: Cloud Sync
                                punch_data = [
                                    new_punch["date"], new_punch["time"], new_punch["emp_id"], 
                                    new_punch["full_name"], new_punch["department"], 
                                    new_punch["punch_type"], new_punch["status"], new_punch["confidence"]
                                ]
                                self.cloud_sync.sync_punch_async(punch_data)
                                
                                self.after(0, self.log_feed, f"[{timestamp}] [LIVE] {emp['full_name']} | {icon} {punch_type} ({status})")
                                self.after(0, self.load_attendance_table)
                            else:
                                msg = f"[{timestamp}] Unknown Finger ID {uid} | 🔴 Unregistered"
                                self.after(0, self.log_feed, msg)
                            print(f"[DEBUG] Logged punch for ID {uid}")
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Failed to communicate with ESP32: {e}")
                self.after(0, self.update_top_bar, f"Device: Disconnected", "🔴")
                fail_count += 1
                if fail_count > 5:
                    print("[DEBUG] Connection lost. Triggering auto-discovery...")
                    self._is_polling = False
                    threading.Thread(target=self.init_discovery, daemon=True).start()
                    break # Exit this poll loop, discovery will start a new one
            time.sleep(1) # Crucial: Don't spam the ESP32 server

if __name__ == "__main__":
    app = AttendanceApp()
    app.mainloop()