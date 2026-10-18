import random
import string

class TaskManager:
    @staticmethod
    def generate_random_gmail() -> dict:
        """সটকে টাস্ক না থাকলে অটো র্যান্ডম জিমেইল জেনারেট করার ফলব্যাক সিস্টেম"""
        first_names = ["sidney", "alex", "david", "michael", "robert", "john", "william", "james"]
        name = random.choice(first_names)
        random_num = ''.join(random.choices(string.digits, k=4))
        random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        
        email = f"{name}{random_num}{random_chars}@gmail.com"
        password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$", k=10))
        recovery = f"rec.{random_chars}@mailtrap.io"
        
        return {
            "id": 0,  # ডামি আইডি
            "email": email,
            "password": password,
            "recovery": recovery,
            "reward": 10.0
        }

task_manager = TaskManager()
