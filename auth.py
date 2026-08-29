import customtkinter as ctk
import configparser
import os

class AuthWindow(ctk.CTkToplevel):
    def __init__(self, master, on_success_callback):
        super().__init__(master)
        
        self.title("Admin Authentication")
        self.geometry("350x250")
        self.resizable(False, False)
        
        # Center the window
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
        
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.on_success = on_success_callback
        self.master_app = master
        
        # Load PIN from config
        self.config = configparser.ConfigParser()
        self.config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
        self.correct_pin = "1234" # Default
        
        if os.path.exists(self.config_path):
            self.config.read(self.config_path)
            if 'Security' in self.config and 'ADMIN_PIN' in self.config['Security']:
                self.correct_pin = self.config['Security']['ADMIN_PIN']
        
        # UI Elements
        ctk.CTkLabel(self, text="🔒 Admin Access", font=("Arial", 22, "bold")).pack(pady=(30, 10))
        ctk.CTkLabel(self, text="Please enter your PIN to continue.", font=("Arial", 12)).pack(pady=(0, 15))
        
        self.pin_entry = ctk.CTkEntry(self, show="*", width=150, justify="center", font=("Arial", 16))
        self.pin_entry.pack(pady=5)
        self.pin_entry.bind("<Return>", self.verify_pin)
        self.pin_entry.focus_set()
        
        self.error_label = ctk.CTkLabel(self, text="", text_color="red", font=("Arial", 11))
        self.error_label.pack()
        
        self.login_btn = ctk.CTkButton(self, text="Login", width=150, command=self.verify_pin)
        self.login_btn.pack(pady=10)
        
    def verify_pin(self, event=None):
        entered_pin = self.pin_entry.get()
        if entered_pin == self.correct_pin:
            self.destroy()
            self.on_success()
        else:
            self.error_label.configure(text="❌ Incorrect PIN. Try again.")
            self.pin_entry.delete(0, 'end')
            
    def on_closing(self):
        self.destroy()
        self.master_app.destroy() # Close entire app if auth window is closed
