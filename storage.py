"""
SQLite persistence layer for the consignment system.

Provides local storage with change tracking to support cloud synchronization.
"""

import sqlite3
import json
from datetime import datetime, date, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager

from core import (
    ItemStatus, Address, SaleRecord, Payout, Item, Consignor, ConsignmentStore
)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def adapt_decimal(d: Decimal) -> str:
    """SQLite adapter for Decimal."""
    return str(d)


def convert_decimal(s: bytes) -> Decimal:
    """SQLite converter for Decimal."""
    return Decimal(s.decode('utf-8'))


def adapt_date(d: date) -> str:
    """SQLite adapter for date."""
    return d.isoformat()


def convert_date(s: bytes) -> date:
    """SQLite converter for date."""
    return date.fromisoformat(s.decode('utf-8'))


# Register adapters and converters
sqlite3.register_adapter(Decimal, adapt_decimal)
sqlite3.register_converter("DECIMAL", convert_decimal)
sqlite3.register_adapter(date, adapt_date)
sqlite3.register_converter("DATE", convert_date)


class ConsignmentStorage:
    """
    SQLite-based persistence for the consignment system.
    
    Tracks changes for cloud synchronization support.
    """

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str = "consignment.db"):
        self.db_path = Path(db_path)
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                -- Schema version tracking
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                
                -- Store configuration (default terms, ID counters)
                CREATE TABLE IF NOT EXISTS store_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    modified_at TEXT NOT NULL,
                    sync_status TEXT DEFAULT 'pending'
                );
                
                -- Consignors
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
                    balance DECIMAL NOT NULL DEFAULT '0.00',
                    created_date DATE NOT NULL,
                    modified_at TEXT NOT NULL,
                    sync_status TEXT DEFAULT 'pending'
                );
                
                -- Items
                CREATE TABLE IF NOT EXISTS items (
                    item_id TEXT PRIMARY KEY,
                    consignor_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    original_price DECIMAL NOT NULL,
                    entry_date DATE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    status_date DATE NOT NULL,
                    modified_at TEXT NOT NULL,
                    sync_status TEXT DEFAULT 'pending',
                    FOREIGN KEY (consignor_id) REFERENCES consignors(consignor_id)
                );
                
                -- Sale records (linked to items)
                CREATE TABLE IF NOT EXISTS sales (
                    item_id TEXT PRIMARY KEY,
                    sale_date DATE NOT NULL,
                    original_price DECIMAL NOT NULL,
                    sale_price DECIMAL NOT NULL,
                    discount_percent INTEGER NOT NULL,
                    stocking_fee DECIMAL NOT NULL,
                    consignor_share DECIMAL NOT NULL,
                    store_share DECIMAL NOT NULL,
                    modified_at TEXT NOT NULL,
                    sync_status TEXT DEFAULT 'pending',
                    FOREIGN KEY (item_id) REFERENCES items(item_id)
                );
                
                -- Payouts
                CREATE TABLE IF NOT EXISTS payouts (
                    payout_id TEXT PRIMARY KEY,
                    consignor_id TEXT NOT NULL,
                    payout_date DATE NOT NULL,
                    amount DECIMAL NOT NULL,
                    check_number TEXT,
                    modified_at TEXT NOT NULL,
                    sync_status TEXT DEFAULT 'pending',
                    FOREIGN KEY (consignor_id) REFERENCES consignors(consignor_id)
                );
                
                -- Sync metadata
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_type TEXT NOT NULL,  -- 'push' or 'pull'
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,  -- 'in_progress', 'success', 'failed'
                    records_synced INTEGER DEFAULT 0,
                    error_message TEXT
                );
                
                -- Indexes for common queries
                CREATE INDEX IF NOT EXISTS idx_items_consignor ON items(consignor_id);
                CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
                CREATE INDEX IF NOT EXISTS idx_items_entry_date ON items(entry_date);
                CREATE INDEX IF NOT EXISTS idx_payouts_consignor ON payouts(consignor_id);
                CREATE INDEX IF NOT EXISTS idx_sync_status_consignors ON consignors(sync_status);
                CREATE INDEX IF NOT EXISTS idx_sync_status_items ON items(sync_status);
                CREATE INDEX IF NOT EXISTS idx_sync_status_sales ON sales(sync_status);
                CREATE INDEX IF NOT EXISTS idx_sync_status_payouts ON payouts(sync_status);
            """)

            # Set schema version if not exists
            conn.execute("""
                INSERT OR IGNORE INTO schema_info (key, value) 
                VALUES ('version', ?)
            """, (str(self.SCHEMA_VERSION),))

    def _now(self) -> str:
        """Current timestamp for modified_at fields."""
        return datetime.now(timezone.utc).isoformat()

    # --- Store Configuration ---

    def save_store_config(self, store: ConsignmentStore):
        """Save store configuration (defaults, counters)."""
        # Get current counter values by peeking (using a helper attribute we'll add)
        # We need to track the "next" value that would be generated
        config = {
            'default_split': str(store.default_split),
            'default_stocking_fee': str(store.default_stocking_fee),
        }

        # For counters, we'll track them via the highest IDs in use
        # This is more robust than trying to serialize itertools.count

        now = self._now()
        with self._get_connection() as conn:
            for key, value in config.items():
                conn.execute("""
                    INSERT OR REPLACE INTO store_config (key, value, modified_at, sync_status)
                    VALUES (?, ?, ?, 'pending')
                """, (key, str(value), now))

            # Save counter states based on highest existing IDs
            # Consignor counter: extract number from highest C#### ID
            consignor_ids = [c.consignor_id for c in store._consignors.values()]
            if consignor_ids:
                max_consignor = max(int(cid[1:]) for cid in consignor_ids)
                conn.execute("""
                    INSERT OR REPLACE INTO store_config (key, value, modified_at, sync_status)
                    VALUES ('consignor_counter', ?, ?, 'pending')
                """, (str(max_consignor + 1), now))

            # Item counter: extract from I###### IDs
            item_ids = [i.item_id for i in store._items.values()]
            if item_ids:
                max_item = max(int(iid[1:]) for iid in item_ids)
                conn.execute("""
                    INSERT OR REPLACE INTO store_config (key, value, modified_at, sync_status)
                    VALUES ('item_counter', ?, ?, 'pending')
                """, (str(max_item + 1), now))

            # Payout counter: extract from P###### IDs
            payout_ids = [p.payout_id for p in store._payouts]
            if payout_ids:
                max_payout = max(int(pid[1:]) for pid in payout_ids)
                conn.execute("""
                    INSERT OR REPLACE INTO store_config (key, value, modified_at, sync_status)
                    VALUES ('payout_counter', ?, ?, 'pending')
                """, (str(max_payout + 1), now))

    def load_store_config(self) -> dict:
        """Load store configuration."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM store_config").fetchall()
            return {row['key']: row['value'] for row in rows}

    # --- Consignor Operations ---

    def save_consignor(self, consignor: Consignor):
        """Save or update a consignor."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO consignors 
                (consignor_id, name, street, city, state, zip_code, phone, email,
                 split_percent, stocking_fee, balance, created_date, modified_at, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (
                consignor.consignor_id,
                consignor.name,
                consignor.address.street,
                consignor.address.city,
                consignor.address.state,
                consignor.address.zip_code,
                consignor.phone,
                consignor.email,
                consignor.split_percent,
                consignor.stocking_fee,
                consignor.balance,
                consignor.created_date,
                self._now()
            ))

    def load_consignor(self, consignor_id: str) -> Optional[Consignor]:
        """Load a consignor by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM consignors WHERE consignor_id = ?",
                (consignor_id,)
            ).fetchone()

            if not row:
                return None

            return self._row_to_consignor(row)

    def load_all_consignors(self) -> list[Consignor]:
        """Load all consignors."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM consignors").fetchall()
            return [self._row_to_consignor(row) for row in rows]

    def _row_to_consignor(self, row: sqlite3.Row) -> Consignor:
        """Convert database row to Consignor object."""
        return Consignor(
            consignor_id=row['consignor_id'],
            name=row['name'],
            address=Address(
                street=row['street'],
                city=row['city'],
                state=row['state'],
                zip_code=row['zip_code']
            ),
            split_percent=Decimal(row['split_percent']),
            stocking_fee=Decimal(row['stocking_fee']),
            balance=Decimal(row['balance']),
            phone=row['phone'],
            email=row['email'],
            created_date=row['created_date'] if isinstance(row['created_date'], date)
            else date.fromisoformat(row['created_date'])
        )

    # --- Item Operations ---

    def save_item(self, item: Item):
        """Save or update an item."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO items
                (item_id, consignor_id, name, description, original_price,
                 entry_date, status, status_date, modified_at, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (
                item.item_id,
                item.consignor_id,
                item.name,
                item.description,
                item.original_price,
                item.entry_date,
                item.status.value,
                item.status_date,
                self._now()
            ))

            # Save sale record if present (in same transaction)
            if item.sale_record:
                sale = item.sale_record
                conn.execute("""
                    INSERT OR REPLACE INTO sales
                    (item_id, sale_date, original_price, sale_price, discount_percent,
                     stocking_fee, consignor_share, store_share, modified_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    sale.item_id,
                    sale.sale_date,
                    sale.original_price,
                    sale.sale_price,
                    sale.discount_percent,
                    sale.stocking_fee,
                    sale.consignor_share,
                    sale.store_share,
                    self._now()
                ))

    def load_item(self, item_id: str) -> Optional[Item]:
        """Load an item by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM items WHERE item_id = ?",
                (item_id,)
            ).fetchone()

            if not row:
                return None

            return self._row_to_item(row, conn)

    def load_all_items(self) -> list[Item]:
        """Load all items."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM items").fetchall()
            return [self._row_to_item(row, conn) for row in rows]

    def load_items_by_consignor(self, consignor_id: str) -> list[Item]:
        """Load all items for a consignor."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM items WHERE consignor_id = ?",
                (consignor_id,)
            ).fetchall()
            return [self._row_to_item(row, conn) for row in rows]

    def _row_to_item(self, row: sqlite3.Row, conn: sqlite3.Connection) -> Item:
        """Convert database row to Item object."""
        # Check for sale record
        sale_row = conn.execute(
            "SELECT * FROM sales WHERE item_id = ?",
            (row['item_id'],)
        ).fetchone()

        sale_record = None
        if sale_row:
            sale_record = SaleRecord(
                item_id=sale_row['item_id'],
                sale_date=sale_row['sale_date'] if isinstance(sale_row['sale_date'], date)
                else date.fromisoformat(sale_row['sale_date']),
                original_price=Decimal(sale_row['original_price']),
                sale_price=Decimal(sale_row['sale_price']),
                discount_percent=sale_row['discount_percent'],
                stocking_fee=Decimal(sale_row['stocking_fee']),
                consignor_share=Decimal(sale_row['consignor_share']),
                store_share=Decimal(sale_row['store_share'])
            )

        entry_date = row['entry_date']
        if not isinstance(entry_date, date):
            entry_date = date.fromisoformat(entry_date)

        status_date = row['status_date']
        if not isinstance(status_date, date):
            status_date = date.fromisoformat(status_date)

        return Item(
            item_id=row['item_id'],
            consignor_id=row['consignor_id'],
            name=row['name'],
            description=row['description'],
            original_price=Decimal(row['original_price']),
            entry_date=entry_date,
            status=ItemStatus(row['status']),
            sale_record=sale_record,
            status_date=status_date
        )

    # --- Sale Record Operations ---

    def save_sale_record(self, sale: SaleRecord):
        """Save a sale record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sales
                (item_id, sale_date, original_price, sale_price, discount_percent,
                 stocking_fee, consignor_share, store_share, modified_at, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (
                sale.item_id,
                sale.sale_date,
                sale.original_price,
                sale.sale_price,
                sale.discount_percent,
                sale.stocking_fee,
                sale.consignor_share,
                sale.store_share,
                self._now()
            ))

    # --- Payout Operations ---

    def save_payout(self, payout: Payout):
        """Save a payout record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO payouts
                (payout_id, consignor_id, payout_date, amount, check_number,
                 modified_at, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """, (
                payout.payout_id,
                payout.consignor_id,
                payout.payout_date,
                payout.amount,
                payout.check_number,
                self._now()
            ))

    def load_all_payouts(self) -> list[Payout]:
        """Load all payouts."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM payouts").fetchall()
            return [self._row_to_payout(row) for row in rows]

    def load_payouts_by_consignor(self, consignor_id: str) -> list[Payout]:
        """Load payouts for a consignor."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM payouts WHERE consignor_id = ?",
                (consignor_id,)
            ).fetchall()
            return [self._row_to_payout(row) for row in rows]

    def _row_to_payout(self, row: sqlite3.Row) -> Payout:
        """Convert database row to Payout object."""
        payout_date = row['payout_date']
        if not isinstance(payout_date, date):
            payout_date = date.fromisoformat(payout_date)

        return Payout(
            payout_id=row['payout_id'],
            consignor_id=row['consignor_id'],
            payout_date=payout_date,
            amount=Decimal(row['amount']),
            check_number=row['check_number']
        )

    # --- Full Store Save/Load ---

    def save_store(self, store: ConsignmentStore):
        """Save the entire store state to database."""
        self.save_store_config(store)

        for consignor in store._consignors.values():
            self.save_consignor(consignor)

        for item in store._items.values():
            self.save_item(item)

        for payout in store._payouts:
            self.save_payout(payout)

    def load_store(self) -> ConsignmentStore:
        """Load full store state from database."""
        import itertools

        config = self.load_store_config()

        # Create store with saved defaults
        store = ConsignmentStore(
            default_split=Decimal(config.get('default_split', '60.00')),
            default_stocking_fee=Decimal(config.get('default_stocking_fee', '2.00'))
        )

        # Restore ID counters
        if 'consignor_counter' in config:
            store._consignor_counter = itertools.count(int(config['consignor_counter']))
        if 'item_counter' in config:
            store._item_counter = itertools.count(int(config['item_counter']))
        if 'payout_counter' in config:
            store._payout_counter = itertools.count(int(config['payout_counter']))

        # Load all data
        for consignor in self.load_all_consignors():
            store._consignors[consignor.consignor_id] = consignor

        for item in self.load_all_items():
            store._items[item.item_id] = item

        store._payouts = self.load_all_payouts()

        return store

    # --- Sync Support ---

    def get_pending_changes(self) -> dict[str, list[dict]]:
        """Get all records with pending sync status."""
        changes = {
            'config': [],
            'consignors': [],
            'items': [],
            'sales': [],
            'payouts': []
        }

        with self._get_connection() as conn:
            # Config
            rows = conn.execute(
                "SELECT * FROM store_config WHERE sync_status = 'pending'"
            ).fetchall()
            changes['config'] = [dict(row) for row in rows]

            # Consignors
            rows = conn.execute(
                "SELECT * FROM consignors WHERE sync_status = 'pending'"
            ).fetchall()
            changes['consignors'] = [dict(row) for row in rows]

            # Items
            rows = conn.execute(
                "SELECT * FROM items WHERE sync_status = 'pending'"
            ).fetchall()
            changes['items'] = [dict(row) for row in rows]

            # Sales
            rows = conn.execute(
                "SELECT * FROM sales WHERE sync_status = 'pending'"
            ).fetchall()
            changes['sales'] = [dict(row) for row in rows]

            # Payouts
            rows = conn.execute(
                "SELECT * FROM payouts WHERE sync_status = 'pending'"
            ).fetchall()
            changes['payouts'] = [dict(row) for row in rows]

        return changes

    def mark_synced(self, table: str, id_column: str, ids: list[str]):
        """Mark records as synced."""
        if not ids:
            return

        with self._get_connection() as conn:
            placeholders = ','.join('?' * len(ids))
            conn.execute(f"""
                UPDATE {table} 
                SET sync_status = 'synced' 
                WHERE {id_column} IN ({placeholders})
            """, ids)

    def mark_all_synced(self):
        """Mark all pending records as synced."""
        with self._get_connection() as conn:
            for table in ['store_config', 'consignors', 'items', 'sales', 'payouts']:
                conn.execute(f"UPDATE {table} SET sync_status = 'synced'")

    def log_sync(self, sync_type: str, status: str,
                 records_synced: int = 0, error_message: str = None) -> int:
        """Log a sync operation."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO sync_log (sync_type, started_at, status, records_synced, error_message)
                VALUES (?, ?, ?, ?, ?)
            """, (sync_type, self._now(), status, records_synced, error_message))
            return cursor.lastrowid

    def update_sync_log(self, log_id: int, status: str,
                        records_synced: int = None, error_message: str = None):
        """Update a sync log entry."""
        with self._get_connection() as conn:
            if records_synced is not None:
                conn.execute("""
                    UPDATE sync_log 
                    SET status = ?, completed_at = ?, records_synced = ?, error_message = ?
                    WHERE id = ?
                """, (status, self._now(), records_synced, error_message, log_id))
            else:
                conn.execute("""
                    UPDATE sync_log 
                    SET status = ?, completed_at = ?, error_message = ?
                    WHERE id = ?
                """, (status, self._now(), error_message, log_id))

    def get_last_sync(self, sync_type: str = None) -> Optional[dict]:
        """Get the most recent sync log entry."""
        with self._get_connection() as conn:
            if sync_type:
                row = conn.execute("""
                    SELECT * FROM sync_log 
                    WHERE sync_type = ? AND status = 'success'
                    ORDER BY completed_at DESC LIMIT 1
                """, (sync_type,)).fetchone()
            else:
                row = conn.execute("""
                    SELECT * FROM sync_log 
                    WHERE status = 'success'
                    ORDER BY completed_at DESC LIMIT 1
                """).fetchone()

            return dict(row) if row else None

    # --- Bulk Import (for recovery) ---

    def clear_all_data(self):
        """Clear all data (for recovery operations)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM sales")
            conn.execute("DELETE FROM payouts")
            conn.execute("DELETE FROM items")
            conn.execute("DELETE FROM consignors")
            conn.execute("DELETE FROM store_config")

    def bulk_import(self, data: dict[str, list[dict]]):
        """
        Import bulk data (from cloud recovery).
        
        Expected format:
        {
            'config': [{'key': ..., 'value': ...}, ...],
            'consignors': [...],
            'items': [...],
            'sales': [...],
            'payouts': [...]
        }
        """
        now = self._now()

        with self._get_connection() as conn:
            # Config
            for row in data.get('config', []):
                conn.execute("""
                    INSERT OR REPLACE INTO store_config (key, value, modified_at, sync_status)
                    VALUES (?, ?, ?, 'synced')
                """, (row['key'], row['value'], now))

            # Consignors
            for row in data.get('consignors', []):
                conn.execute("""
                    INSERT OR REPLACE INTO consignors
                    (consignor_id, name, street, city, state, zip_code, phone, email,
                     split_percent, stocking_fee, balance, created_date, modified_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'synced')
                """, (
                    row['consignor_id'], row['name'], row['street'], row['city'],
                    row['state'], row['zip_code'], row.get('phone'), row.get('email'),
                    row['split_percent'], row['stocking_fee'], row['balance'],
                    row['created_date'], now
                ))

            # Items
            for row in data.get('items', []):
                conn.execute("""
                    INSERT OR REPLACE INTO items
                    (item_id, consignor_id, name, description, original_price,
                     entry_date, status, status_date, modified_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'synced')
                """, (
                    row['item_id'], row['consignor_id'], row['name'], row['description'],
                    row['original_price'], row['entry_date'], row['status'],
                    row['status_date'], now
                ))

            # Sales
            for row in data.get('sales', []):
                conn.execute("""
                    INSERT OR REPLACE INTO sales
                    (item_id, sale_date, original_price, sale_price, discount_percent,
                     stocking_fee, consignor_share, store_share, modified_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'synced')
                """, (
                    row['item_id'], row['sale_date'], row['original_price'],
                    row['sale_price'], row['discount_percent'], row['stocking_fee'],
                    row['consignor_share'], row['store_share'], now
                ))

            # Payouts
            for row in data.get('payouts', []):
                conn.execute("""
                    INSERT OR REPLACE INTO payouts
                    (payout_id, consignor_id, payout_date, amount, check_number,
                     modified_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, 'synced')
                """, (
                    row['payout_id'], row['consignor_id'], row['payout_date'],
                    row['amount'], row.get('check_number'), now
                ))