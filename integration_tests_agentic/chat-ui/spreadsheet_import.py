#  Copyright 2025 Dell Inc. or its subsidiaries. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


"""
Spreadsheet Import Utilities

Handles CSV and Excel import of iDRAC credentials.
"""

import pandas as pd
import io
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SpreadsheetImporter:
    """Import credentials from CSV or Excel files."""

    # Expected column names (case-insensitive)
    REQUIRED_COLUMNS = ["system_id", "idrac_ip", "username", "password"]
    OPTIONAL_COLUMNS = ["auth_token", "description"]

    @staticmethod
    def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column names to lowercase with underscores.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with normalized column names
        """
        # Convert to lowercase and replace spaces/hyphens with underscores
        df.columns = df.columns.str.lower().str.replace(' ', '_').str.replace('-', '_')
        return df

    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> tuple[bool, List[str]]:
        """
        Validate that DataFrame has required columns.

        Args:
            df: Input DataFrame

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check for required columns
        missing_cols = [col for col in SpreadsheetImporter.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            errors.append(f"Missing required columns: {', '.join(missing_cols)}")

        # Check for empty required fields
        for col in SpreadsheetImporter.REQUIRED_COLUMNS:
            if col in df.columns and df[col].isna().any():
                empty_rows = df[df[col].isna()].index.tolist()
                errors.append(f"Column '{col}' has empty values in rows: {empty_rows}")

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def import_from_csv(file_content: bytes) -> tuple[List[Dict[str, Any]], List[str]]:
        """
        Import credentials from CSV file content.

        Args:
            file_content: Raw CSV file bytes

        Returns:
            Tuple of (list_of_credentials, list_of_errors)
        """
        try:
            # Read CSV
            df = pd.read_csv(io.BytesIO(file_content))

            # Normalize column names
            df = SpreadsheetImporter.normalize_column_names(df)

            # Validate
            is_valid, errors = SpreadsheetImporter.validate_dataframe(df)
            if not is_valid:
                return [], errors

            # Convert to list of dictionaries
            credentials = []
            for _, row in df.iterrows():
                cred = {
                    "system_id": str(row["system_id"]).strip(),
                    "idrac_ip": str(row["idrac_ip"]).strip(),
                    "username": str(row["username"]).strip(),
                    "password": str(row["password"]).strip(),
                }

                # Add optional fields if present
                if "auth_token" in row and pd.notna(row["auth_token"]):
                    cred["auth_token"] = str(row["auth_token"]).strip()

                if "description" in row and pd.notna(row["description"]):
                    cred["description"] = str(row["description"]).strip()

                credentials.append(cred)

            logger.info(f"Successfully parsed {len(credentials)} credentials from CSV")
            return credentials, []

        except Exception as e:
            logger.error(f"Error importing CSV: {e}")
            return [], [f"Failed to parse CSV: {str(e)}"]

    @staticmethod
    def import_from_excel(file_content: bytes, sheet_name: Optional[str] = None) -> tuple[List[Dict[str, Any]], List[str]]:
        """
        Import credentials from Excel file content.

        Args:
            file_content: Raw Excel file bytes
            sheet_name: Name of sheet to import (defaults to first sheet)

        Returns:
            Tuple of (list_of_credentials, list_of_errors)
        """
        try:
            # Read Excel (first sheet by default)
            df = pd.read_excel(io.BytesIO(file_content), sheet_name=sheet_name or 0)

            # Normalize column names
            df = SpreadsheetImporter.normalize_column_names(df)

            # Validate
            is_valid, errors = SpreadsheetImporter.validate_dataframe(df)
            if not is_valid:
                return [], errors

            # Convert to list of dictionaries
            credentials = []
            for _, row in df.iterrows():
                cred = {
                    "system_id": str(row["system_id"]).strip(),
                    "idrac_ip": str(row["idrac_ip"]).strip(),
                    "username": str(row["username"]).strip(),
                    "password": str(row["password"]).strip(),
                }

                # Add optional fields if present
                if "auth_token" in row and pd.notna(row["auth_token"]):
                    cred["auth_token"] = str(row["auth_token"]).strip()

                if "description" in row and pd.notna(row["description"]):
                    cred["description"] = str(row["description"]).strip()

                credentials.append(cred)

            logger.info(f"Successfully parsed {len(credentials)} credentials from Excel")
            return credentials, []

        except Exception as e:
            logger.error(f"Error importing Excel: {e}")
            return [], [f"Failed to parse Excel: {str(e)}"]

    @staticmethod
    def create_template_csv() -> str:
        """
        Create a CSV template for credential import.

        Returns:
            CSV template string
        """
        template_data = {
            "system_id": ["server-01", "server-02", "server-03"],
            "idrac_ip": ["https://192.168.1.100", "https://192.168.1.101", "https://192.168.1.102"],
            "username": ["root", "admin", "root"],
            "password": ["password123", "password456", "password789"],
            "auth_token": ["", "", ""],
            "description": ["Production Server 1", "Development Server", "Test Server"]
        }

        df = pd.DataFrame(template_data)
        return df.to_csv(index=False)

    @staticmethod
    def create_template_excel() -> bytes:
        """
        Create an Excel template for credential import.

        Returns:
            Excel file bytes
        """
        template_data = {
            "system_id": ["server-01", "server-02", "server-03"],
            "idrac_ip": ["https://192.168.1.100", "https://192.168.1.101", "https://192.168.1.102"],
            "username": ["root", "admin", "root"],
            "password": ["password123", "password456", "password789"],
            "auth_token": ["", "", ""],
            "description": ["Production Server 1", "Development Server", "Test Server"]
        }

        df = pd.DataFrame(template_data)

        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='iDRAC Credentials')

        return output.getvalue()
