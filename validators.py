"""
Task Submission Validation Module
Implements strict input formatting rules for platform task submissions
"""

import re
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Validation result with error details."""
    is_valid: bool
    message: str
    cleaned_value: Optional[str] = None


class TaskValidator:
    """Strict validator for different task types."""

    # Gmail validation
    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
    )

    # Facebook validation
    FB_UID_PATTERN = re.compile(r"^\d{1,20}$")
    FB_COOKIE_PATTERN = re.compile(r"^[a-zA-Z0-9\-_=]{10,}$")

    # Instagram validation
    INSTA_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._]{1,30}$")
    INSTA_2FA_PATTERN = re.compile(r"^\d{6}$")

    @staticmethod
    def validate_gmail_address(email: str) -> ValidationResult:
        """
        Validate Gmail address format.
        Rules:
        - Must be valid email format
        - Length: 5-64 characters
        - Must contain @gmail.com domain
        """
        if not email or not isinstance(email, str):
            return ValidationResult(False, "❌ ইমেইল প্রদান করুন।")

        email = email.strip().lower()

        # Length validation
        if len(email) < 5 or len(email) > 64:
            return ValidationResult(
                False,
                f"❌ ইমেইল দৈর্ঘ্য 5-64 অক্ষর হতে হবে। বর্তমান: {len(email)} অক্ষর।"
            )

        # Domain validation
        if not email.endswith("@gmail.com"):
            return ValidationResult(
                False,
                "❌ শুধুমাত্র Gmail ঠিকানা (@gmail.com) গ্রহণযোগ্য।"
            )

        # Format validation
        if not TaskValidator.EMAIL_PATTERN.match(email):
            return ValidationResult(
                False,
                "❌ ইমেইল ফর্ম্যাট অবৈধ। বিশেষ অক্ষর পরীক্ষা করুন।"
            )

        return ValidationResult(
            True,
            "✅ ইমেইল বৈধ।",
            cleaned_value=email
        )

    @staticmethod
    def validate_facebook_uid(uid: str) -> ValidationResult:
        """
        Validate Facebook UID.
        Rules:
        - Must be numeric
        - Length: 1-20 digits
        - No special characters
        """
        if not uid or not isinstance(uid, str):
            return ValidationResult(False, "❌ Facebook UID প্রদান করুন।")

        uid = uid.strip()

        if not TaskValidator.FB_UID_PATTERN.match(uid):
            return ValidationResult(
                False,
                "❌ Facebook UID শুধুমাত্র সংখ্যা থাকতে পারে (1-20 ডিজিট)।"
            )

        return ValidationResult(
            True,
            "✅ Facebook UID বৈধ।",
            cleaned_value=uid
        )

    @staticmethod
    def validate_facebook_cookies(cookies: str) -> ValidationResult:
        """
        Validate Facebook cookies string.
        Rules:
        - Minimum 10 characters
        - Alphanumeric, hyphens, underscores
        - Maximum 5000 characters
        """
        if not cookies or not isinstance(cookies, str):
            return ValidationResult(False, "❌ কুকিজ প্রদান করুন।")

        cookies = cookies.strip()

        if len(cookies) < 10:
            return ValidationResult(
                False,
                "❌ কুকিজ খুব ছোট (ন্যূনতম 10 অক্ষর)।"
            )

        if len(cookies) > 5000:
            return ValidationResult(
                False,
                "❌ কুকিজ খুব বড় (সর্বোচ্চ 5000 অক্ষর)।"
            )

        if not TaskValidator.FB_COOKIE_PATTERN.match(cookies):
            return ValidationResult(
                False,
                "❌ কুকিজ ফর্ম্যাট অবৈধ। অনুমোদিত অক্ষর: a-z, A-Z, 0-9, -, _"
            )

        return ValidationResult(
            True,
            "✅ কুকিজ বৈধ।",
            cleaned_value=cookies
        )

    @staticmethod
    def validate_instagram_username(username: str) -> ValidationResult:
        """
        Validate Instagram username.
        Rules:
        - 1-30 characters
        - Letters, numbers, periods, underscores only
        - Cannot start/end with period
        """
        if not username or not isinstance(username, str):
            return ValidationResult(False, "❌ Instagram ইউজারনেম প্রদান করুন।")

        username = username.strip().lower()

        if len(username) < 1 or len(username) > 30:
            return ValidationResult(
                False,
                "❌ Instagram ইউজারনেম 1-30 অক্ষর হতে হবে।"
            )

        if not TaskValidator.INSTA_USERNAME_PATTERN.match(username):
            return ValidationResult(
                False,
                "❌ Instagram ইউজারনেম শুধুমাত্র অক্ষর, সংখ্যা, ডট, আন্ডারস্কোর ব্যবহার করতে পারে।"
            )

        if username.startswith(".") or username.endswith("."):
            return ValidationResult(
                False,
                "❌ Instagram ইউজারনেম ডট দিয়ে শুরু বা শেষ হতে পারে না।"
            )

        return ValidationResult(
            True,
            "✅ Instagram ইউজারনেম বৈধ।",
            cleaned_value=username
        )

    @staticmethod
    def validate_instagram_2fa(code: str) -> ValidationResult:
        """
        Validate Instagram 2FA code.
        Rules:
        - Exactly 6 digits
        - Numeric only
        """
        if not code or not isinstance(code, str):
            return ValidationResult(False, "❌ 2FA কোড প্রদান করুন।")

        code = code.strip()

        if not TaskValidator.INSTA_2FA_PATTERN.match(code):
            return ValidationResult(
                False,
                "❌ 2FA কোড ঠিক 6 সংখ্যা হতে হবে।"
            )

        return ValidationResult(
            True,
            "✅ 2FA কোড বৈধ।",
            cleaned_value=code
        )

    @staticmethod
    def validate_string_length(
        value: str,
        min_length: int = 1,
        max_length: int = 1000,
        field_name: str = "মান",
    ) -> ValidationResult:
        """
        Generic string length validation.
        """
        if not value or not isinstance(value, str):
            return ValidationResult(False, f"❌ {field_name} প্রদান করুন।")

        length = len(value)

        if length < min_length:
            return ValidationResult(
                False,
                f"❌ {field_name} কমপক্ষে {min_length} অক্ষর হতে হবে। বর্তমান: {length}"
            )

        if length > max_length:
            return ValidationResult(
                False,
                f"❌ {field_name} সর্বোচ্চ {max_length} অক্ষর হতে পারে। বর্তমান: {length}"
            )

        return ValidationResult(True, "✅ বৈধ।", cleaned_value=value.strip())

    @staticmethod
    def validate_numeric_only(
        value: str,
        field_name: str = "মান",
        allow_decimals: bool = False,
    ) -> ValidationResult:
        """
        Validate numeric-only input.
        """
        if not value or not isinstance(value, str):
            return ValidationResult(False, f"❌ {field_name} প্রদান করুন।")

        value = value.strip()
        pattern = r"^\d+(\.\d+)?$" if allow_decimals else r"^\d+$"

        if not re.match(pattern, value):
            decimal_note = " বা দশমিক সহ" if allow_decimals else ""
            return ValidationResult(
                False,
                f"❌ {field_name} শুধুমাত্র সংখ্যা{decimal_note} হতে পারে।"
            )

        return ValidationResult(True, "✅ বৈধ।", cleaned_value=value)

    @staticmethod
    def sanitize_submission_data(data: dict) -> dict:
        """
        Sanitize submission data to prevent injection attacks.
        """
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Remove null bytes and extreme whitespace
                value = value.replace("\x00", "").strip()
                # Limit length
                value = value[:5000]
            sanitized[key] = value
        return sanitized


# Preset validation rules by task category
VALIDATION_RULES = {
    "gmail": {
        "email": TaskValidator.validate_gmail_address,
    },
    "facebook": {
        "uid": TaskValidator.validate_facebook_uid,
        "cookies": TaskValidator.validate_facebook_cookies,
    },
    "instagram": {
        "username": TaskValidator.validate_instagram_username,
        "2fa_code": TaskValidator.validate_instagram_2fa,
    },
}


async def validate_task_submission(
    task_category: str,
    submission_data: dict,
) -> Tuple[bool, str, Optional[dict]]:
    """
    Validate task submission based on category.
    
    Returns:
        (is_valid, error_message, cleaned_data)
    """
    try:
        # Sanitize first
        cleaned_data = TaskValidator.sanitize_submission_data(submission_data)

        # Get rules for this category
        rules = VALIDATION_RULES.get(task_category, {})
        if not rules:
            return False, f"❌ অজানা টাস্ক বিভাগ: {task_category}", None

        # Validate each required field
        for field, validator in rules.items():
            if field not in cleaned_data:
                return False, f"❌ প্রয়োজনীয় ফিল্ড অনুপস্থিত: {field}", None

            result = validator(cleaned_data[field])
            if not result.is_valid:
                return False, result.message, None

            # Replace with cleaned value
            cleaned_data[field] = result.cleaned_value

        return True, "✅ সাবমিশন বৈধ।", cleaned_data

    except Exception as e:
        logger.exception(f"Error validating submission: {e}")
        return False, "⚠️ যাচাইকরণে ত্রুটি। পুনরায় চেষ্টা করুন।", None
