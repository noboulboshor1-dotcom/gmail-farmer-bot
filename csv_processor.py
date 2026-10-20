"""
CSV Processing Module for Admin Operations
Handles safe bulk imports/exports of user earnings, referral commissions, and pending tasks
"""

import csv
import io
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

BD_TZ = timezone(timedelta(hours=6))


@dataclass
class CSVImportResult:
    """Result of CSV import operation."""
    success: bool
    total_rows: int
    processed_rows: int
    skipped_rows: int
    errors: List[str]
    stats: dict  # {success_count, failed_count, etc.}


class CSVProcessor:
    """Handle CSV import/export operations for admin features."""

    # CSV headers for different export types
    PENDING_SUBMISSIONS_HEADERS = [
        "submission_id",
        "user_id",
        "task_id",
        "submission_data",
        "status",
        "created_at",
        "updated_at",
    ]

    EARNINGS_UPDATE_HEADERS = [
        "user_id",
        "amount",
        "reason",
    ]

    REFERRAL_COMMISSION_HEADERS = [
        "referrer_id",
        "commission_amount",
    ]

    USER_EARNINGS_REPORT_HEADERS = [
        "user_id",
        "username",
        "balance",
        "completed_tasks",
        "referral_count",
        "referral_income",
        "is_banned",
    ]

    @staticmethod
    def export_pending_submissions_csv(submissions: List[dict]) -> str:
        """
        Export pending submissions to CSV format.
        
        Args:
            submissions: List of submission dictionaries from database
            
        Returns:
            CSV content as string
        """
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=CSVProcessor.PENDING_SUBMISSIONS_HEADERS,
        )

        writer.writeheader()

        for sub in submissions:
            # Flatten submission_data if it's a dict
            submission_data_str = sub.get("submission_data", "")
            if isinstance(submission_data_str, dict):
                submission_data_str = str(submission_data_str)

            writer.writerow({
                "submission_id": sub.get("id", ""),
                "user_id": sub.get("user_id", ""),
                "task_id": sub.get("task_id", ""),
                "submission_data": submission_data_str,
                "status": sub.get("status", ""),
                "created_at": sub.get("created_at", ""),
                "updated_at": sub.get("updated_at", ""),
            })

        return output.getvalue()

    @staticmethod
    def export_user_earnings_csv(users: List[dict]) -> str:
        """
        Export user earnings report.
        
        Args:
            users: List of user dictionaries
            
        Returns:
            CSV content as string
        """
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=CSVProcessor.USER_EARNINGS_REPORT_HEADERS,
        )

        writer.writeheader()

        for user in users:
            writer.writerow({
                "user_id": user.get("user_id", ""),
                "username": user.get("username", "Unknown"),
                "balance": user.get("balance", 0.0),
                "completed_tasks": user.get("completed_tasks", 0),
                "referral_count": user.get("referral_count", 0),
                "referral_income": user.get("referral_income", 0.0),
                "is_banned": user.get("is_banned", False),
            })

        return output.getvalue()

    @staticmethod
    def parse_earnings_update_csv(csv_content: str) -> Tuple[List[Tuple[int, float, str]], List[str]]:
        """
        Parse CSV for bulk earnings updates.
        
        Format:
        user_id,amount,reason
        12345,100.50,completed_task_batch_1
        67890,-50.00,balance_correction
        
        Args:
            csv_content: Raw CSV content string
            
        Returns:
            (updates_list, errors_list)
            updates_list: [(user_id, delta_amount, reason), ...]
        """
        updates = []
        errors = []

        try:
            reader = csv.DictReader(io.StringIO(csv_content))

            if not reader.fieldnames:
                return [], ["❌ খালি CSV ফাইল।"]

            if not all(h in reader.fieldnames for h in ["user_id", "amount", "reason"]):
                return [], [f"❌ প্রয়োজনীয় কলাম অনুপস্থিত। প্রয়োজনীয়: {CSVProcessor.EARNINGS_UPDATE_HEADERS}"]

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (after header)
                try:
                    user_id_str = row.get("user_id", "").strip()
                    amount_str = row.get("amount", "").strip()
                    reason = row.get("reason", "manual_update").strip()

                    # Validate user_id
                    if not user_id_str or not user_id_str.isdigit():
                        errors.append(f"Row {row_num}: অবৈধ user_id = '{user_id_str}'")
                        continue

                    user_id = int(user_id_str)

                    # Validate amount
                    try:
                        amount = float(amount_str)
                        if not amount:  # Skip zero amounts
                            errors.append(f"Row {row_num}: শূন্য পরিমাণ, বাদ দেওয়া হয়েছে।")
                            continue
                    except ValueError:
                        errors.append(f"Row {row_num}: অবৈধ পরিমাণ = '{amount_str}'")
                        continue

                    # Validate reason
                    if not reason or len(reason) > 100:
                        errors.append(f"Row {row_num}: অবৈধ কারণ দৈর্ঘ্য।")
                        continue

                    updates.append((user_id, amount, reason))

                except Exception as e:
                    errors.append(f"Row {row_num}: প্রসেসিং ত্রুটি - {str(e)}")

        except Exception as e:
            logger.exception("Error parsing earnings CSV")
            errors.append(f"❌ CSV পার্সিং ত্রুটি: {str(e)}")

        return updates, errors

    @staticmethod
    def parse_referral_commission_csv(csv_content: str) -> Tuple[dict, List[str]]:
        """
        Parse CSV for referral commission distribution.
        
        Format:
        referrer_id,commission_amount
        12345,50.00
        67890,75.50
        
        Args:
            csv_content: Raw CSV content string
            
        Returns:
            (commissions_dict, errors_list)
            commissions_dict: {referrer_id: commission_amount, ...}
        """
        commissions = {}
        errors = []

        try:
            reader = csv.DictReader(io.StringIO(csv_content))

            if not reader.fieldnames:
                return {}, ["❌ খালি CSV ফাইল।"]

            if not all(h in reader.fieldnames for h in ["referrer_id", "commission_amount"]):
                return {}, [f"❌ প্রয়োজনীয় কলাম অনুপস্থিত। প্রয়োজনীয়: {CSVProcessor.REFERRAL_COMMISSION_HEADERS}"]

            for row_num, row in enumerate(reader, start=2):
                try:
                    referrer_id_str = row.get("referrer_id", "").strip()
                    commission_str = row.get("commission_amount", "").strip()

                    if not referrer_id_str or not referrer_id_str.isdigit():
                        errors.append(f"Row {row_num}: অবৈধ referrer_id = '{referrer_id_str}'")
                        continue

                    referrer_id = int(referrer_id_str)

                    try:
                        commission = float(commission_str)
                        if commission <= 0:
                            errors.append(f"Row {row_num}: নেতিবাচক বা শূন্য কমিশন, বাদ দেওয়া।")
                            continue
                    except ValueError:
                        errors.append(f"Row {row_num}: অবৈধ কমিশন = '{commission_str}'")
                        continue

                    # Allow multiple rows for same referrer (they get summed)
                    if referrer_id in commissions:
                        commissions[referrer_id] += commission
                    else:
                        commissions[referrer_id] = commission

                except Exception as e:
                    errors.append(f"Row {row_num}: প্রসেসিং ত্রুটি - {str(e)}")

        except Exception as e:
            logger.exception("Error parsing referral commission CSV")
            errors.append(f"❌ CSV পার্সিং ত্রুটি: {str(e)}")

        return commissions, errors

    @staticmethod
    def generate_csv_file(
        headers: List[str],
        rows: List[dict],
        filename_prefix: str = "export",
    ) -> Tuple[str, bytes]:
        """
        Generate CSV file content as bytes.
        
        Returns:
            (filename, csv_bytes)
        """
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers)

        writer.writeheader()
        for row in rows:
            writer.writerow(row)

        csv_content = output.getvalue()
        csv_bytes = csv_content.encode('utf-8')

        timestamp = datetime.now(BD_TZ).strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.csv"

        return filename, csv_bytes

    @staticmethod
    def validate_csv_structure(
        csv_content: str,
        required_headers: List[str],
    ) -> Tuple[bool, str]:
        """
        Validate CSV structure before processing.
        
        Returns:
            (is_valid, error_message)
        """
        try:
            reader = csv.DictReader(io.StringIO(csv_content))

            if not reader.fieldnames:
                return False, "❌ খালি CSV ফাইল।"

            missing = set(required_headers) - set(reader.fieldnames or [])
            if missing:
                return False, f"❌ প্রয়োজনীয় কলাম অনুপস্থিত: {', '.join(missing)}"

            # Count data rows
            row_count = 0
            for _ in reader:
                row_count += 1

            if row_count == 0:
                return False, "❌ কোন ডেটা রো নেই (শুধুমাত্র হেডার)।"

            return True, f"✅ {row_count} রো পাওয়া গেছে।"

        except Exception as e:
            logger.exception("Error validating CSV structure")
            return False, f"❌ CSV বৈধতা ত্রুটি: {str(e)}"


async def safe_import_earnings_updates(
    db,
    csv_content: str,
) -> CSVImportResult:
    """
    Safely import and apply earnings updates from CSV.
    Uses atomic delta updates to prevent race conditions.
    
    Args:
        db: Database instance
        csv_content: Raw CSV content
        
    Returns:
        CSVImportResult with detailed stats
    """
    # Validate structure first
    is_valid, msg = CSVProcessor.validate_csv_structure(
        csv_content,
        CSVProcessor.EARNINGS_UPDATE_HEADERS,
    )

    if not is_valid:
        return CSVImportResult(
            success=False,
            total_rows=0,
            processed_rows=0,
            skipped_rows=0,
            errors=[msg],
            stats={},
        )

    # Parse CSV
    updates, parse_errors = CSVProcessor.parse_earnings_update_csv(csv_content)

    if not updates:
        return CSVImportResult(
            success=False,
            total_rows=len(parse_errors),
            processed_rows=0,
            skipped_rows=len(parse_errors),
            errors=parse_errors,
            stats={},
        )

    # Apply updates using database atomic operations
    stats = await db.bulk_update_balances(updates)

    return CSVImportResult(
        success=stats["failed_count"] == 0,
        total_rows=len(updates),
        processed_rows=stats["success_count"],
        skipped_rows=stats["failed_count"],
        errors=stats["errors"],
        stats=stats,
    )


async def safe_import_referral_commissions(
    db,
    csv_content: str,
) -> CSVImportResult:
    """
    Safely import and distribute referral commissions from CSV.
    
    Args:
        db: Database instance
        csv_content: Raw CSV content
        
    Returns:
        CSVImportResult with distribution stats
    """
    # Validate structure
    is_valid, msg = CSVProcessor.validate_csv_structure(
        csv_content,
        CSVProcessor.REFERRAL_COMMISSION_HEADERS,
    )

    if not is_valid:
        return CSVImportResult(
            success=False,
            total_rows=0,
            processed_rows=0,
            skipped_rows=0,
            errors=[msg],
            stats={},
        )

    # Parse commissions
    commissions, parse_errors = CSVProcessor.parse_referral_commission_csv(csv_content)

    if not commissions:
        return CSVImportResult(
            success=False,
            total_rows=len(parse_errors),
            processed_rows=0,
            skipped_rows=len(parse_errors),
            errors=parse_errors,
            stats={},
        )

    # Distribute commissions
    stats = await db.bulk_distribute_referral_commissions(commissions)

    return CSVImportResult(
        success=stats["failed_count"] == 0,
        total_rows=len(commissions),
        processed_rows=stats["success_count"],
        skipped_rows=stats["failed_count"],
        errors=parse_errors + stats["errors"],
        stats=stats,
    )
