import random
import string

class TaskManager:
    def generate_random_gmail(self):
        """একটি অটোমেটেড টেস্ট জিমেইল ইউজারনেম ও পাসওয়ার্ড তৈরি করে"""
        first_names = ["rahim", "karim", "tanvir", "sakib", "hasan", "arif", "sabbir"]
        last_names = ["ahmed", "khan", "chowdhury", "mia", "hossain", "islam"]
        
        name = f"{random.choice(first_names)}{random.choice(last_names)}"
        digits = "".join(random.choices(string.digits, k=4))
        username = f"{name}{digits}@gmail.com"
        
        # পাসওয়ার্ড জেনারেটর
        chars = string.ascii_letters + string.digits + "@#$"
        password = "".join(random.choices(chars, k=10))
        
        # রিকভারি ইমেইল
        recovery_email = f"rec.{digits}@mailtrap.io"
        
        return {
            "email": username,
            "password": password,
            "recovery": recovery_email,
            "reward": 10.0  # প্রতি জিমেইলের জন্য ১০ টাকা
        }

task_manager = TaskManager()
