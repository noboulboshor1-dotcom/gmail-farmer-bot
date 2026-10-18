import random
import string

class TaskManager:
    @staticmethod
    def generate_random_gmail() -> dict:
        """ইনবক্স ভেরিফিকেশন সুবিধা সহ রিকভারি মেইল জেনারেট করা"""
        first_names = ["sidney", "alex", "david", "michael", "robert", "john", "william", "james"]
        name = random.choice(first_names)
        random_num = ''.join(random.choices(string.digits, k=4))
        random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        
        email = f"{name}{random_num}{random_chars}@gmail.com"
        password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$", k=10))
        
        # 1secmail-এর সাপোর্ট ডোমেইন ব্যবহার
        domain = "1secmail.com"
        recovery_username = f"rec_{random_chars}"
        recovery = f"{recovery_username}@{domain}"
        
        return {
            "id": 0,
            "email": email,
            "password": password,
            "recovery": recovery,
            "recovery_user": recovery_username,
            "recovery_domain": domain,
            "reward": 10.0
        }

task_manager = TaskManager()
