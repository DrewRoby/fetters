"""
Cloud synchronization module for the consignment system.

Provides backup and recovery via PostgreSQL cloud database.
This module is designed as a stub that can be configured with
actual cloud database credentials.
"""

import os
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum

from storage import ConsignmentStorage


class SyncDirection(Enum):
    """Direction of sync operation."""
    PUSH = "push"      # Local -> Cloud
    PULL = "pull"      # Cloud -> Local (recovery)


class SyncStatus(Enum):
    """Status of sync operation."""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    NO_CHANGES = "no_changes"


@dataclass
class SyncResult:
    """Result of a sync operation."""
    direction: SyncDirection
    status: SyncStatus
    records_synced: int
    error_message: Optional[str] = None
    details: Optional[dict] = None


@dataclass
class CloudConfig:
    """Configuration for cloud database connection."""
    host: str
    port: int
    database: str
    user: str
    password: str
    ssl_mode: str = "require"
    
    @classmethod
    def from_env(cls) -> Optional['CloudConfig']:
        """
        Load configuration from environment variables.
        
        Expected variables:
            CONSIGNMENT_CLOUD_HOST
            CONSIGNMENT_CLOUD_PORT
            CONSIGNMENT_CLOUD_DATABASE
            CONSIGNMENT_CLOUD_USER
            CONSIGNMENT_CLOUD_PASSWORD
            CONSIGNMENT_CLOUD_SSL_MODE (optional, default: require)
        """
        host = os.environ.get('CONSIGNMENT_CLOUD_HOST')
        if not host:
            return None
        
        return cls(
            host=host,
            port=int(os.environ.get('CONSIGNMENT_CLOUD_PORT', '5432')),
            database=os.environ.get('CONSIGNMENT_CLOUD_DATABASE', 'consignment'),
            user=os.environ.get('CONSIGNMENT_CLOUD_USER', ''),
            password=os.environ.get('CONSIGNMENT_CLOUD_PASSWORD', ''),
            ssl_mode=os.environ.get('CONSIGNMENT_CLOUD_SSL_MODE', 'require')
        )
    
    @classmethod
    def from_url(cls, url: str) -> 'CloudConfig':
        """
        Parse a PostgreSQL connection URL.
        
        Format: postgresql://user:password@host:port/database?sslmode=require
        """
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        
        return cls(
            host=parsed.hostname or 'localhost',
            port=parsed.port or 5432,
            database=parsed.path.lstrip('/') or 'consignment',
            user=parsed.username or '',
            password=parsed.password or '',
            ssl_mode=query.get('sslmode', ['require'])[0]
        )
    
    def to_connection_string(self) -> str:
        """Generate psycopg2 connection string."""
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password} sslmode={self.ssl_mode}"
        )


class CloudSync:
    """
    Cloud synchronization handler for PostgreSQL backup.
    
    Usage:
        # Option 1: From environment variables
        sync = CloudSync(local_storage)
        if sync.is_configured():
            result = sync.push_changes()
        
        # Option 2: Explicit configuration
        config = CloudConfig(host='...', port=5432, ...)
        sync = CloudSync(local_storage, config)
        result = sync.push_changes()
        
        # Option 3: From connection URL
        config = CloudConfig.from_url('postgresql://user:pass@host/db')
        sync = CloudSync(local_storage, config)
    """
    
    def __init__(
        self, 
        local_storage: ConsignmentStorage,
        cloud_config: Optional[CloudConfig] = None
    ):
        self.local = local_storage
        self.config = cloud_config or CloudConfig.from_env()
        self._connection = None
    
    def is_configured(self) -> bool:
        """Check if cloud connection is configured."""
        return self.config is not None
    
    def test_connection(self) -> tuple[bool, str]:
        """
        Test the cloud database connection.
        
        Returns:
            (success, message) tuple
        """
        if not self.is_configured():
            return False, "Cloud database not configured"
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            self._close_connection()
            return True, "Connection successful"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
    def _get_connection(self):
        """Get or create database connection."""
        if self._connection is None:
            try:
                import psycopg2
            except ImportError:
                raise ImportError(
                    "psycopg2 is required for cloud sync. "
                    "Install with: pip install psycopg2-binary"
                )
            
            self._connection = psycopg2.connect(self.config.to_connection_string())
        return self._connection
    
    def _close_connection(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def _ensure_schema(self):
        """Ensure cloud database has required schema."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS store_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                modified_at TIMESTAMP NOT NULL,
                source_instance TEXT
            );
            
            CREATE TABLE IF NOT EXISTS consignors (
                consignor_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                street TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                split_percent DECIMAL NOT NULL,
                stocking_fee DECIMAL NOT NULL,
                balance DECIMAL NOT NULL,
                created_date DATE NOT NULL,
                modified_at TIMESTAMP NOT NULL,
                source_instance TEXT
            );
            
            CREATE TABLE IF NOT EXISTS items (
                item_id TEXT PRIMARY KEY,
                consignor_id TEXT NOT NULL REFERENCES consignors(consignor_id),
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                original_price DECIMAL NOT NULL,
                entry_date DATE NOT NULL,
                status TEXT NOT NULL,
                status_date DATE NOT NULL,
                modified_at TIMESTAMP NOT NULL,
                source_instance TEXT
            );
            
            CREATE TABLE IF NOT EXISTS sales (
                item_id TEXT PRIMARY KEY REFERENCES items(item_id),
                sale_date DATE NOT NULL,
                original_price DECIMAL NOT NULL,
                sale_price DECIMAL NOT NULL,
                discount_percent INTEGER NOT NULL,
                stocking_fee DECIMAL NOT NULL,
                consignor_share DECIMAL NOT NULL,
                store_share DECIMAL NOT NULL,
                modified_at TIMESTAMP NOT NULL,
                source_instance TEXT
            );
            
            CREATE TABLE IF NOT EXISTS payouts (
                payout_id TEXT PRIMARY KEY,
                consignor_id TEXT NOT NULL REFERENCES consignors(consignor_id),
                payout_date DATE NOT NULL,
                amount DECIMAL NOT NULL,
                check_number TEXT,
                modified_at TIMESTAMP NOT NULL,
                source_instance TEXT
            );
            
            CREATE TABLE IF NOT EXISTS sync_history (
                id SERIAL PRIMARY KEY,
                sync_type TEXT NOT NULL,
                source_instance TEXT,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                status TEXT NOT NULL,
                records_synced INTEGER DEFAULT 0,
                error_message TEXT
            );
            
            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_cloud_items_consignor ON items(consignor_id);
            CREATE INDEX IF NOT EXISTS idx_cloud_payouts_consignor ON payouts(consignor_id);
        """)
        
        conn.commit()
        cursor.close()
    
    def _get_instance_id(self) -> str:
        """Get a unique identifier for this local instance."""
        import socket
        import hashlib
        
        # Combine hostname and db path for unique ID
        hostname = socket.gethostname()
        db_path = str(self.local.db_path.absolute())
        
        unique = f"{hostname}:{db_path}"
        return hashlib.sha256(unique.encode()).hexdigest()[:12]
    
    # --- Push (Local -> Cloud) ---
    
    def push_changes(self) -> SyncResult:
        """
        Push pending local changes to cloud database.
        
        Only syncs records marked as 'pending' in local storage.
        """
        if not self.is_configured():
            return SyncResult(
                direction=SyncDirection.PUSH,
                status=SyncStatus.FAILED,
                records_synced=0,
                error_message="Cloud database not configured"
            )
        
        log_id = self.local.log_sync('push', 'in_progress')
        
        try:
            self._ensure_schema()
            conn = self._get_connection()
            cursor = conn.cursor()
            
            changes = self.local.get_pending_changes()
            instance_id = self._get_instance_id()
            total_synced = 0
            
            # Sync config
            for row in changes['config']:
                cursor.execute("""
                    INSERT INTO store_config (key, value, modified_at, source_instance)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (key) DO UPDATE SET 
                        value = EXCLUDED.value,
                        modified_at = EXCLUDED.modified_at,
                        source_instance = EXCLUDED.source_instance
                """, (row['key'], row['value'], row['modified_at'], instance_id))
                total_synced += 1
            
            # Sync consignors
            for row in changes['consignors']:
                cursor.execute("""
                    INSERT INTO consignors 
                    (consignor_id, name, street, city, state, zip_code, phone, email,
                     split_percent, stocking_fee, balance, created_date, modified_at, source_instance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (consignor_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        street = EXCLUDED.street,
                        city = EXCLUDED.city,
                        state = EXCLUDED.state,
                        zip_code = EXCLUDED.zip_code,
                        phone = EXCLUDED.phone,
                        email = EXCLUDED.email,
                        split_percent = EXCLUDED.split_percent,
                        stocking_fee = EXCLUDED.stocking_fee,
                        balance = EXCLUDED.balance,
                        modified_at = EXCLUDED.modified_at,
                        source_instance = EXCLUDED.source_instance
                """, (
                    row['consignor_id'], row['name'], row['street'], row['city'],
                    row['state'], row['zip_code'], row['phone'], row['email'],
                    row['split_percent'], row['stocking_fee'], row['balance'],
                    row['created_date'], row['modified_at'], instance_id
                ))
                total_synced += 1
            
            # Sync items
            for row in changes['items']:
                cursor.execute("""
                    INSERT INTO items
                    (item_id, consignor_id, name, description, original_price,
                     entry_date, status, status_date, modified_at, source_instance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        status = EXCLUDED.status,
                        status_date = EXCLUDED.status_date,
                        modified_at = EXCLUDED.modified_at,
                        source_instance = EXCLUDED.source_instance
                """, (
                    row['item_id'], row['consignor_id'], row['name'], row['description'],
                    row['original_price'], row['entry_date'], row['status'],
                    row['status_date'], row['modified_at'], instance_id
                ))
                total_synced += 1
            
            # Sync sales
            for row in changes['sales']:
                cursor.execute("""
                    INSERT INTO sales
                    (item_id, sale_date, original_price, sale_price, discount_percent,
                     stocking_fee, consignor_share, store_share, modified_at, source_instance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO UPDATE SET
                        sale_date = EXCLUDED.sale_date,
                        sale_price = EXCLUDED.sale_price,
                        discount_percent = EXCLUDED.discount_percent,
                        consignor_share = EXCLUDED.consignor_share,
                        store_share = EXCLUDED.store_share,
                        modified_at = EXCLUDED.modified_at,
                        source_instance = EXCLUDED.source_instance
                """, (
                    row['item_id'], row['sale_date'], row['original_price'],
                    row['sale_price'], row['discount_percent'], row['stocking_fee'],
                    row['consignor_share'], row['store_share'], row['modified_at'], instance_id
                ))
                total_synced += 1
            
            # Sync payouts
            for row in changes['payouts']:
                cursor.execute("""
                    INSERT INTO payouts
                    (payout_id, consignor_id, payout_date, amount, check_number,
                     modified_at, source_instance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (payout_id) DO UPDATE SET
                        payout_date = EXCLUDED.payout_date,
                        amount = EXCLUDED.amount,
                        check_number = EXCLUDED.check_number,
                        modified_at = EXCLUDED.modified_at,
                        source_instance = EXCLUDED.source_instance
                """, (
                    row['payout_id'], row['consignor_id'], row['payout_date'],
                    row['amount'], row['check_number'], row['modified_at'], instance_id
                ))
                total_synced += 1
            
            conn.commit()
            cursor.close()
            
            # Mark local records as synced
            self.local.mark_all_synced()
            
            self.local.update_sync_log(log_id, 'success', total_synced)
            
            status = SyncStatus.SUCCESS if total_synced > 0 else SyncStatus.NO_CHANGES
            return SyncResult(
                direction=SyncDirection.PUSH,
                status=status,
                records_synced=total_synced
            )
            
        except Exception as e:
            self.local.update_sync_log(log_id, 'failed', error_message=str(e))
            return SyncResult(
                direction=SyncDirection.PUSH,
                status=SyncStatus.FAILED,
                records_synced=0,
                error_message=str(e)
            )
        finally:
            self._close_connection()
    
    def push_full(self) -> SyncResult:
        """
        Push ALL local data to cloud (full backup).
        
        Unlike push_changes(), this syncs everything regardless of sync status.
        """
        if not self.is_configured():
            return SyncResult(
                direction=SyncDirection.PUSH,
                status=SyncStatus.FAILED,
                records_synced=0,
                error_message="Cloud database not configured"
            )
        
        # Temporarily mark everything as pending
        with self.local._get_connection() as conn:
            for table in ['store_config', 'consignors', 'items', 'sales', 'payouts']:
                conn.execute(f"UPDATE {table} SET sync_status = 'pending'")
        
        return self.push_changes()
    
    # --- Pull (Cloud -> Local) ---
    
    def pull_full(self, confirm: bool = False) -> SyncResult:
        """
        Recover all data from cloud to local.
        
        WARNING: This will REPLACE all local data!
        
        Args:
            confirm: Must be True to proceed (safety check)
        """
        if not confirm:
            return SyncResult(
                direction=SyncDirection.PULL,
                status=SyncStatus.FAILED,
                records_synced=0,
                error_message="Recovery not confirmed. Pass confirm=True to proceed."
            )
        
        if not self.is_configured():
            return SyncResult(
                direction=SyncDirection.PULL,
                status=SyncStatus.FAILED,
                records_synced=0,
                error_message="Cloud database not configured"
            )
        
        log_id = self.local.log_sync('pull', 'in_progress')
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            data = {
                'config': [],
                'consignors': [],
                'items': [],
                'sales': [],
                'payouts': []
            }
            total = 0
            
            # Fetch config
            cursor.execute("SELECT key, value FROM store_config")
            for row in cursor.fetchall():
                data['config'].append({'key': row[0], 'value': row[1]})
                total += 1
            
            # Fetch consignors
            cursor.execute("""
                SELECT consignor_id, name, street, city, state, zip_code,
                       phone, email, split_percent, stocking_fee, balance, created_date
                FROM consignors
            """)
            for row in cursor.fetchall():
                data['consignors'].append({
                    'consignor_id': row[0],
                    'name': row[1],
                    'street': row[2],
                    'city': row[3],
                    'state': row[4],
                    'zip_code': row[5],
                    'phone': row[6],
                    'email': row[7],
                    'split_percent': str(row[8]),
                    'stocking_fee': str(row[9]),
                    'balance': str(row[10]),
                    'created_date': row[11].isoformat() if hasattr(row[11], 'isoformat') else row[11]
                })
                total += 1
            
            # Fetch items
            cursor.execute("""
                SELECT item_id, consignor_id, name, description, original_price,
                       entry_date, status, status_date
                FROM items
            """)
            for row in cursor.fetchall():
                data['items'].append({
                    'item_id': row[0],
                    'consignor_id': row[1],
                    'name': row[2],
                    'description': row[3],
                    'original_price': str(row[4]),
                    'entry_date': row[5].isoformat() if hasattr(row[5], 'isoformat') else row[5],
                    'status': row[6],
                    'status_date': row[7].isoformat() if hasattr(row[7], 'isoformat') else row[7]
                })
                total += 1
            
            # Fetch sales
            cursor.execute("""
                SELECT item_id, sale_date, original_price, sale_price,
                       discount_percent, stocking_fee, consignor_share, store_share
                FROM sales
            """)
            for row in cursor.fetchall():
                data['sales'].append({
                    'item_id': row[0],
                    'sale_date': row[1].isoformat() if hasattr(row[1], 'isoformat') else row[1],
                    'original_price': str(row[2]),
                    'sale_price': str(row[3]),
                    'discount_percent': row[4],
                    'stocking_fee': str(row[5]),
                    'consignor_share': str(row[6]),
                    'store_share': str(row[7])
                })
                total += 1
            
            # Fetch payouts
            cursor.execute("""
                SELECT payout_id, consignor_id, payout_date, amount, check_number
                FROM payouts
            """)
            for row in cursor.fetchall():
                data['payouts'].append({
                    'payout_id': row[0],
                    'consignor_id': row[1],
                    'payout_date': row[2].isoformat() if hasattr(row[2], 'isoformat') else row[2],
                    'amount': str(row[3]),
                    'check_number': row[4]
                })
                total += 1
            
            cursor.close()
            
            # Clear local and import
            self.local.clear_all_data()
            self.local.bulk_import(data)
            
            self.local.update_sync_log(log_id, 'success', total)
            
            return SyncResult(
                direction=SyncDirection.PULL,
                status=SyncStatus.SUCCESS,
                records_synced=total,
                details={'tables': {k: len(v) for k, v in data.items()}}
            )
            
        except Exception as e:
            self.local.update_sync_log(log_id, 'failed', error_message=str(e))
            return SyncResult(
                direction=SyncDirection.PULL,
                status=SyncStatus.FAILED,
                records_synced=0,
                error_message=str(e)
            )
        finally:
            self._close_connection()
    
    def get_cloud_summary(self) -> Optional[dict]:
        """
        Get a summary of what's in the cloud database.
        
        Useful to check before recovery.
        """
        if not self.is_configured():
            return None
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            summary = {}
            
            tables = ['consignors', 'items', 'sales', 'payouts']
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                summary[table] = cursor.fetchone()[0]
            
            # Get last sync time
            cursor.execute("""
                SELECT completed_at, source_instance 
                FROM sync_history 
                WHERE status = 'success' 
                ORDER BY completed_at DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                summary['last_sync'] = row[0].isoformat() if row[0] else None
                summary['last_sync_source'] = row[1]
            
            cursor.close()
            return summary
            
        except Exception as e:
            return {'error': str(e)}
        finally:
            self._close_connection()


# --- Convenience Functions ---

def setup_auto_sync(
    local_storage: ConsignmentStorage,
    cloud_config: Optional[CloudConfig] = None,
    sync_interval_minutes: int = 15
) -> Optional['AutoSync']:
    """
    Set up automatic background sync.
    
    Returns an AutoSync instance that can be started/stopped,
    or None if cloud is not configured.
    """
    sync = CloudSync(local_storage, cloud_config)
    if not sync.is_configured():
        return None
    
    return AutoSync(sync, sync_interval_minutes)


class AutoSync:
    """
    Automatic background sync handler.
    
    Note: This is a stub. In production, you'd use threading or
    an async scheduler. For now, call sync_if_due() periodically.
    """
    
    def __init__(self, cloud_sync: CloudSync, interval_minutes: int = 15):
        self.cloud_sync = cloud_sync
        self.interval_minutes = interval_minutes
        self._last_sync: Optional[datetime] = None
        self._running = False
    
    def sync_if_due(self) -> Optional[SyncResult]:
        """
        Sync if enough time has passed since last sync.
        
        Call this periodically (e.g., on app idle, after transactions).
        """
        now = datetime.utcnow()
        
        if self._last_sync:
            elapsed = (now - self._last_sync).total_seconds() / 60
            if elapsed < self.interval_minutes:
                return None
        
        result = self.cloud_sync.push_changes()
        if result.status in (SyncStatus.SUCCESS, SyncStatus.NO_CHANGES):
            self._last_sync = now
        
        return result
    
    def force_sync(self) -> SyncResult:
        """Force an immediate sync."""
        result = self.cloud_sync.push_changes()
        if result.status in (SyncStatus.SUCCESS, SyncStatus.NO_CHANGES):
            self._last_sync = datetime.utcnow()
        return result
