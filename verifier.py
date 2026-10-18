import aiohttp
import logging

logger = logging.getLogger(__name__)

async def check_recovery_email_received(recovery_email: str) -> bool:
    """
    গুগল থেকে রিকভারি ইনবক্সে নোটিফিকেশন মেইল এসেছে কি না চেক করা
    """
    try:
        if "@" not in recovery_email:
            return False
            
        username, domain = recovery_email.split("@")
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={username}&domain={domain}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    messages = await response.json()
                    # ইনবক্সে কোনো মেইল এসেছে কি না তা পরীক্ষা করা
                    if len(messages) > 0:
                        logger.info(f"Verification success for {recovery_email}")
                        return True
        return False
    except Exception as e:
        logger.error(f"Verification error for {recovery_email}: {e}")
        return False
