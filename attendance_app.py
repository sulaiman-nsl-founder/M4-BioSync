import customtkinter as ctk
import requests
import threading
import time

# --- CONFIGURATION ---
# Replace with the IP address printed in your ESP32 Serial Monitor
ESP32_IP = "http://192.168.137.11" 

class AttendanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Smart Attendance System")
        self.geometry("500x400")
        
        # --- UI LAYOUT ---
        self.title_label = ctk.CTkLabel(self, text="Attendance Dashboard", font=("Arial", 24, "bold"))
        self.title_label.pack(pady=20)
        
        self.status_label = ctk.CTkLabel(self, text="Connecting to ESP32...", font=("Arial", 16), text_color="orange")
        self.status_label.pack(pady=10)
        
        # Enrollment Section
        self.enroll_frame = ctk.CTkFrame(self)
        self.enroll_frame.pack(pady=20, padx=20, fill="x")
        
        self.id_entry = ctk.CTkEntry(self.enroll_frame, placeholder_text="Enter ID (1-127)")
        self.id_entry.pack(side="left", padx=10, pady=10, expand=True)
        
        self.enroll_btn = ctk.CTkButton(self.enroll_frame, text="Enroll User", command=self.start_enrollment)
        self.enroll_btn.pack(side="right", padx=10, pady=10)
        
        # Log Box
        self.log_box = ctk.CTkTextbox(self, height=120)
        self.log_box.pack(pady=10, padx=20, fill="both", expand=True)
        
        # --- START BACKGROUND POLLING ---
        self.is_running = True
        self.poll_thread = threading.Thread(target=self.poll_esp32)
        self.poll_thread.daemon = True
        self.poll_thread.start()

    def start_enrollment(self):
        user_id = self.id_entry.get()
        if user_id.isdigit():
            try:
                requests.get(f"{ESP32_IP}/start_enroll?id={user_id}", timeout=3)
                self.log(f"Started enrollment for ID: {user_id}")
            except Exception as e:
                self.log("Error: Could not reach ESP32.")
        else:
            self.log("Please enter a valid numeric ID.")

    def poll_esp32(self):
        """Continuously asks the ESP32 for its current status in the background."""
        while self.is_running:
            try:
                response = requests.get(f"{ESP32_IP}/status", timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Update status text
                    self.status_label.configure(text=data["status"], text_color="green")
                    
                    # If a new finger was scanned, log it
                    if data["last_id"] != -1:
                        self.log(f"User ID {data['last_id']} successfully scanned!")
                        
            except requests.exceptions.RequestException:
                self.status_label.configure(text="Disconnected from ESP32", text_color="red")
            
            time.sleep(1) # Wait 1 second before asking again

    def log(self, message):
        """Helper to print messages to the text box"""
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

if __name__ == "__main__":
    app = AttendanceApp()
    app.mainloop()
    