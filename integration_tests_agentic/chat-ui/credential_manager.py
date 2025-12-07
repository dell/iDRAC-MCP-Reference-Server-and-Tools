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
Encrypted Credential Manager

Manages iDRAC credentials with encrypted SQLite storage.
"""

import sqlite3
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import base64
import logging

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


@dataclass
class iDRACCredential:
    """iDRAC credential record."""
    system_id: str
    idrac_ip: str
    username: str
    password: str
    auth_token: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def get_connection_dict(self) -> Dict[str, str]:
        """Get connection dictionary for MCP tools."""
        return {
            "idrac_ip": self.idrac_ip,
            "username": self.username,
            "password": self.password,
            "auth_token": self.auth_token
        }


class CredentialEncryption:
    """Handles encryption/decryption of credentials."""

    def __init__(self, master_password: Optional[str] = None):
        """
        Initialize encryption handler.

        Args:
            master_password: Master password for encryption (optional, uses default if not provided)
        """
        # Use environment variable or default password
        # In production, this should be configured per-deployment
        password = master_password or os.getenv("CREDENTIAL_MASTER_PASSWORD", "changeme-in-production")

        # Derive encryption key from password using PBKDF2
        salt = b'idrac-credential-salt-v1'  # Static salt (should be unique per deployment in production)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        self.cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string."""
        if not plaintext:
            return ""
        return self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext string."""
        if not ciphertext:
            return ""
        return self.cipher.decrypt(ciphertext.encode()).decode()


class CredentialDatabase:
    """Encrypted SQLite database for iDRAC credentials."""

    def __init__(self, db_path: Optional[str] = None, master_password: Optional[str] = None):
        """
        Initialize credential database.

        Args:
            db_path: Path to SQLite database file
            master_password: Master password for encryption
        """
        # Default to ~/.idrac_credentials.db
        if db_path is None:
            db_path = os.path.expanduser("~/.idrac_credentials.db")

        self.db_path = db_path
        self.encryption = CredentialEncryption(master_password)
        self._init_database()

    def _init_database(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create credentials table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                system_id TEXT PRIMARY KEY,
                idrac_ip TEXT NOT NULL,
                username_encrypted TEXT NOT NULL,
                password_encrypted TEXT NOT NULL,
                auth_token_encrypted TEXT,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Create index on idrac_ip for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_idrac_ip ON credentials(idrac_ip)
        """)

        conn.commit()
        conn.close()

        logger.info(f"Credential database initialized at {self.db_path}")

    def add_credential(self, credential: iDRACCredential) -> bool:
        """
        Add or update a credential.

        Args:
            credential: iDRAC credential to add

        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Encrypt sensitive fields
            username_enc = self.encryption.encrypt(credential.username)
            password_enc = self.encryption.encrypt(credential.password)
            auth_token_enc = self.encryption.encrypt(credential.auth_token) if credential.auth_token else None

            # Set timestamps
            now = datetime.now().isoformat()
            created_at = credential.created_at or now
            updated_at = now

            # Insert or replace credential
            cursor.execute("""
                INSERT OR REPLACE INTO credentials
                (system_id, idrac_ip, username_encrypted, password_encrypted,
                 auth_token_encrypted, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                credential.system_id,
                credential.idrac_ip,
                username_enc,
                password_enc,
                auth_token_enc,
                credential.description,
                created_at,
                updated_at
            ))

            conn.commit()
            conn.close()

            logger.info(f"Credential added/updated for system: {credential.system_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding credential: {e}")
            return False

    def get_credential(self, system_id: str) -> Optional[iDRACCredential]:
        """
        Get credential by system ID.

        Args:
            system_id: System identifier

        Returns:
            iDRACCredential or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT system_id, idrac_ip, username_encrypted, password_encrypted,
                       auth_token_encrypted, description, created_at, updated_at
                FROM credentials
                WHERE system_id = ?
            """, (system_id,))

            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            # Decrypt sensitive fields
            username = self.encryption.decrypt(row[2])
            password = self.encryption.decrypt(row[3])
            auth_token = self.encryption.decrypt(row[4]) if row[4] else None

            return iDRACCredential(
                system_id=row[0],
                idrac_ip=row[1],
                username=username,
                password=password,
                auth_token=auth_token,
                description=row[5],
                created_at=row[6],
                updated_at=row[7]
            )

        except Exception as e:
            logger.error(f"Error getting credential: {e}")
            return None

    def list_credentials(self) -> List[Dict[str, Any]]:
        """
        List all credentials (without decrypting sensitive fields).

        Returns:
            List of credential summaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT system_id, idrac_ip, description, created_at, updated_at
                FROM credentials
                ORDER BY system_id
            """)

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "system_id": row[0],
                    "idrac_ip": row[1],
                    "description": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error listing credentials: {e}")
            return []

    def delete_credential(self, system_id: str) -> bool:
        """
        Delete a credential.

        Args:
            system_id: System identifier

        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM credentials WHERE system_id = ?", (system_id,))

            conn.commit()
            conn.close()

            logger.info(f"Credential deleted for system: {system_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting credential: {e}")
            return False

    def import_from_list(self, credentials: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Import multiple credentials from a list.

        Args:
            credentials: List of credential dictionaries

        Returns:
            Dictionary with import statistics
        """
        stats = {"success": 0, "failed": 0, "errors": []}

        for cred_dict in credentials:
            try:
                # Validate required fields
                required_fields = ["system_id", "idrac_ip", "username", "password"]
                if not all(field in cred_dict for field in required_fields):
                    stats["failed"] += 1
                    stats["errors"].append(f"Missing required fields in: {cred_dict.get('system_id', 'unknown')}")
                    continue

                # Create credential object
                credential = iDRACCredential(
                    system_id=cred_dict["system_id"],
                    idrac_ip=cred_dict["idrac_ip"],
                    username=cred_dict["username"],
                    password=cred_dict["password"],
                    auth_token=cred_dict.get("auth_token"),
                    description=cred_dict.get("description")
                )

                # Add to database
                if self.add_credential(credential):
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
                    stats["errors"].append(f"Failed to add: {credential.system_id}")

            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append(f"Error processing credential: {e}")

        return stats

    def export_to_list(self, include_passwords: bool = False) -> List[Dict[str, Any]]:
        """
        Export all credentials to a list.

        Args:
            include_passwords: If True, include decrypted passwords (USE WITH CAUTION)

        Returns:
            List of credential dictionaries
        """
        if include_passwords:
            # Get all credentials with decryption
            credentials = []
            for summary in self.list_credentials():
                cred = self.get_credential(summary["system_id"])
                if cred:
                    credentials.append(cred.to_dict())
            return credentials
        else:
            # Return summary without passwords
            return self.list_credentials()
