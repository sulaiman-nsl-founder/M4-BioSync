import pandas as pd
import os
from datetime import datetime

class DataManager:
    def __init__(self, file_path="employees.csv"):
        self.file_path = file_path
        self.columns = ["emp_id", "full_name", "department", "designation", "finger_id", "enrolled_date", "status"]
        if not os.path.exists(self.file_path):
            df = pd.DataFrame(columns=self.columns)
            df.to_csv(self.file_path, index=False)

    def load_employees(self):
        return pd.read_csv(self.file_path, dtype={"finger_id": "Int64", "emp_id": str})

    def add_employee(self, emp_id, full_name, department, designation, finger_id):
        df = self.load_employees()
        
        # Check if already exists (re-enrollment)
        if not df[df["emp_id"] == emp_id].empty:
            df.loc[df["emp_id"] == emp_id, "finger_id"] = finger_id
            df.loc[df["emp_id"] == emp_id, "status"] = "Active"
        else:
            new_row = {
                "emp_id": emp_id,
                "full_name": full_name,
                "department": department,
                "designation": designation,
                "finger_id": finger_id,
                "enrolled_date": datetime.now().strftime("%Y-%m-%d"),
                "status": "Active"
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            
        df.to_csv(self.file_path, index=False)

    def update_employee(self, emp_id, full_name, department, designation):
        df = self.load_employees()
        df.loc[df["emp_id"] == emp_id, ["full_name", "department", "designation"]] = [full_name, department, designation]
        df.to_csv(self.file_path, index=False)

    def deactivate_employee(self, emp_id):
        df = self.load_employees()
        df.loc[df["emp_id"] == emp_id, "status"] = "Inactive"
        df.to_csv(self.file_path, index=False)
        
    def hard_delete_employee(self, emp_id):
        df = self.load_employees()
        df = df[df["emp_id"] != emp_id]
        df.to_csv(self.file_path, index=False)

    def get_employee_by_finger_id(self, finger_id):
        df = self.load_employees()
        match = df[(df["finger_id"] == int(finger_id)) & (df["status"] == "Active")]
        if not match.empty:
            return match.iloc[0].to_dict()
        return None
        
    def get_next_finger_id(self):
        df = self.load_employees()
        if df.empty or df["finger_id"].isnull().all():
            return 1
        return int(df["finger_id"].max()) + 1
