import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import threading

class SheetsSync:
    def __init__(self):
        self.scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        self.creds_file = "credentials.json"
        self.client = None
        self.sheet = None
        self.is_configured = False
        
        self._authenticate()

    def _authenticate(self):
        if not os.path.exists(self.creds_file):
            print("[CLOUD] Missing credentials.json. Cloud sync disabled.")
            self.is_configured = False
            return
            
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.creds_file, self.scope)
            self.client = gspread.authorize(creds)
            # Try to open the sheet, or create it if it doesn't exist
            sheet_name = "BioSync_Attendance_Log"
            try:
                self.sheet = self.client.open(sheet_name).sheet1
            except gspread.exceptions.SpreadsheetNotFound:
                # We can't automatically create a sheet in their root drive easily without broader permissions,
                # so we instruct the user to create one named "BioSync_Attendance_Log" and share it with the service account.
                print(f"[CLOUD] Spreadsheet '{sheet_name}' not found. Please create it and share it with the service account email.")
                self.is_configured = False
                return
                
            self.is_configured = True
            print("[CLOUD] Google Sheets connected successfully!")
            
            # Ensure headers exist
            if not self.sheet.row_values(1):
                self.sheet.append_row(["Date", "Time", "Emp ID", "Name", "Department", "Punch Type", "Status", "Confidence"])
                
        except Exception as e:
            print(f"[CLOUD] Authentication failed: {e}")
            self.is_configured = False

    def sync_punch_async(self, punch_data):
        """
        punch_data should be a list: [date, time, emp_id, name, dept, type, status, confidence]
        """
        if not self.is_configured:
            return
            
        def _push():
            try:
                self.sheet.append_row(punch_data)
                print(f"[CLOUD] Successfully synced punch for {punch_data[3]} to Google Sheets.")
            except Exception as e:
                print(f"[CLOUD] Failed to sync to Google Sheets: {e}")
                # Here we could implement an offline queue in the future (Task 5.14)
                
        threading.Thread(target=_push, daemon=True).start()
