import logging
import aiohttp

logger = logging.getLogger(__name__)

class InboxVerifier:
    def __init__(self):
        self.base_url = "https://www.1secmail.com/api/v1/"

    async def check_inbox(self, email: str) -> bool:
        """ইমেইলের ইনবক্স চেক করে ভেরিফিকেশন মেইল এসেছে কি না তা নিশ্চিত করা"""
        try:
            if "@" not in email:
                return False
            
            login, domain = email.split("@")
            url = f"{self.base_url}?action=getMessages&login={login}&domain={domain}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        messages = await response.json()
                        if messages and len(messages) > 0:
                            logger.info(f"✅ Email verification success for {email}")
                            return True
            return False
        except Exception as e:
            logger.error(f"Error checking inbox for {email}: {e}")
            return False

# main.py যে নামটি দিয়ে ইম্পোর্ট করছে সেটি সঠিকভাবে তৈরি করা হলো
inbox_verifier = InboxVerifier()
