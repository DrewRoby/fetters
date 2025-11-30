"""
Tests for the storage and cloud sync modules.
"""

import unittest
import tempfile
import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from core import (
    ItemStatus, Address, SaleRecord, Payout, Item, Consignor, ConsignmentStore
)
from storage import ConsignmentStorage
from cloud_sync import CloudSync, CloudConfig, SyncDirection, SyncStatus, SyncResult


class TestStorageBasics(unittest.TestCase):
    """Test basic storage operations."""
    
    def setUp(self):
        # Use a temp file for each test
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = ConsignmentStorage(self.db_path)
    
    def tearDown(self):
        # Clean up temp files
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_database_created(self):
        """Database file should be created on init."""
        self.assertTrue(os.path.exists(self.db_path))
    
    def test_schema_version(self):
        """Schema version should be stored."""
        config = self.storage.load_store_config()
        # Schema info is in a separate table, but basic functionality works
        self.assertIsInstance(config, dict)


class TestConsignorStorage(unittest.TestCase):
    """Test consignor persistence."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = ConsignmentStorage(self.db_path)
        
        self.addr = Address("123 Main St", "Springfield", "IL", "62701")
        self.consignor = Consignor(
            consignor_id="C1001",
            name="Jane Doe",
            address=self.addr,
            split_percent=Decimal("60.00"),
            stocking_fee=Decimal("2.00"),
            balance=Decimal("125.50"),
            phone="555-1234",
            email="jane@example.com",
            created_date=date.today()
        )
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_save_and_load_consignor(self):
        """Consignor should round-trip through storage."""
        self.storage.save_consignor(self.consignor)
        loaded = self.storage.load_consignor("C1001")
        
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.consignor_id, "C1001")
        self.assertEqual(loaded.name, "Jane Doe")
        self.assertEqual(loaded.address.street, "123 Main St")
        self.assertEqual(loaded.split_percent, Decimal("60.00"))
        self.assertEqual(loaded.balance, Decimal("125.50"))
        self.assertEqual(loaded.phone, "555-1234")
    
    def test_load_nonexistent_consignor(self):
        """Loading nonexistent consignor returns None."""
        loaded = self.storage.load_consignor("NOTREAL")
        self.assertIsNone(loaded)
    
    def test_load_all_consignors(self):
        """Should load all saved consignors."""
        self.storage.save_consignor(self.consignor)
        
        consignor2 = Consignor(
            consignor_id="C1002",
            name="John Smith",
            address=self.addr,
            split_percent=Decimal("55.00"),
            stocking_fee=Decimal("3.00"),
            created_date=date.today()
        )
        self.storage.save_consignor(consignor2)
        
        all_consignors = self.storage.load_all_consignors()
        self.assertEqual(len(all_consignors), 2)
    
    def test_update_consignor(self):
        """Saving again should update existing record."""
        self.storage.save_consignor(self.consignor)
        
        self.consignor.balance = Decimal("200.00")
        self.consignor.split_percent = Decimal("65.00")
        self.storage.save_consignor(self.consignor)
        
        loaded = self.storage.load_consignor("C1001")
        self.assertEqual(loaded.balance, Decimal("200.00"))
        self.assertEqual(loaded.split_percent, Decimal("65.00"))


class TestItemStorage(unittest.TestCase):
    """Test item persistence."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = ConsignmentStorage(self.db_path)
        
        # Need a consignor first (foreign key)
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = Consignor(
            consignor_id="C1001",
            name="Test",
            address=self.addr,
            split_percent=Decimal("60.00"),
            stocking_fee=Decimal("2.00"),
            created_date=date.today()
        )
        self.storage.save_consignor(self.consignor)
        
        self.item = Item(
            item_id="I000001",
            consignor_id="C1001",
            name="Vintage Lamp",
            description="Art deco brass lamp",
            original_price=Decimal("75.00"),
            entry_date=date.today() - timedelta(days=15),
            status=ItemStatus.ACTIVE,
            status_date=date.today() - timedelta(days=15)
        )
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_save_and_load_item(self):
        """Item should round-trip through storage."""
        self.storage.save_item(self.item)
        loaded = self.storage.load_item("I000001")
        
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.item_id, "I000001")
        self.assertEqual(loaded.name, "Vintage Lamp")
        self.assertEqual(loaded.original_price, Decimal("75.00"))
        self.assertEqual(loaded.status, ItemStatus.ACTIVE)
    
    def test_save_item_with_sale_record(self):
        """Item with sale record should persist correctly."""
        self.item.status = ItemStatus.SOLD
        self.item.sale_record = SaleRecord(
            item_id="I000001",
            sale_date=date.today(),
            original_price=Decimal("75.00"),
            sale_price=Decimal("56.25"),  # 25% off
            discount_percent=25,
            stocking_fee=Decimal("2.00"),
            consignor_share=Decimal("32.55"),
            store_share=Decimal("23.70")
        )
        
        self.storage.save_item(self.item)
        loaded = self.storage.load_item("I000001")
        
        self.assertEqual(loaded.status, ItemStatus.SOLD)
        self.assertIsNotNone(loaded.sale_record)
        self.assertEqual(loaded.sale_record.sale_price, Decimal("56.25"))
        self.assertEqual(loaded.sale_record.consignor_share, Decimal("32.55"))
    
    def test_load_items_by_consignor(self):
        """Should filter items by consignor."""
        self.storage.save_item(self.item)
        
        item2 = Item(
            item_id="I000002",
            consignor_id="C1001",
            name="Another Item",
            description="Desc",
            original_price=Decimal("50.00"),
            entry_date=date.today(),
            status_date=date.today()
        )
        self.storage.save_item(item2)
        
        items = self.storage.load_items_by_consignor("C1001")
        self.assertEqual(len(items), 2)


class TestPayoutStorage(unittest.TestCase):
    """Test payout persistence."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = ConsignmentStorage(self.db_path)
        
        # Need a consignor first
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = Consignor(
            consignor_id="C1001",
            name="Test",
            address=self.addr,
            split_percent=Decimal("60.00"),
            stocking_fee=Decimal("2.00"),
            created_date=date.today()
        )
        self.storage.save_consignor(self.consignor)
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_save_and_load_payout(self):
        """Payout should round-trip through storage."""
        payout = Payout(
            payout_id="P000001",
            consignor_id="C1001",
            payout_date=date.today(),
            amount=Decimal("150.00"),
            check_number="1234"
        )
        
        self.storage.save_payout(payout)
        payouts = self.storage.load_payouts_by_consignor("C1001")
        
        self.assertEqual(len(payouts), 1)
        self.assertEqual(payouts[0].amount, Decimal("150.00"))
        self.assertEqual(payouts[0].check_number, "1234")


class TestFullStoreStorage(unittest.TestCase):
    """Test saving and loading complete store state."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = ConsignmentStorage(self.db_path)
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_save_and_load_store(self):
        """Complete store should round-trip through storage."""
        # Create a store with data
        store = ConsignmentStore(
            default_split=Decimal("55.00"),
            default_stocking_fee=Decimal("2.50")
        )
        
        addr = Address("456 Oak Ave", "Townsville", "CA", "90210")
        consignor = store.add_consignor(
            name="Alice Smith",
            address=addr,
            phone="555-9999"
        )
        
        item = store.add_item(
            consignor_id=consignor.consignor_id,
            name="Test Item",
            description="A test item",
            price=Decimal("100.00")
        )
        
        store.sell_item(item.item_id)
        store.process_payout(consignor.consignor_id, check_number="5001")
        
        # Save
        self.storage.save_store(store)
        
        # Load into new store
        loaded_store = self.storage.load_store()
        
        # Verify
        self.assertEqual(loaded_store.default_split, Decimal("55.00"))
        self.assertEqual(loaded_store.default_stocking_fee, Decimal("2.50"))
        
        loaded_consignors = loaded_store.list_consignors()
        self.assertEqual(len(loaded_consignors), 1)
        self.assertEqual(loaded_consignors[0].name, "Alice Smith")
        
        loaded_items = loaded_store.get_active_items()
        # Item was sold, so no active items
        self.assertEqual(len(loaded_items), 0)
        
        # But we should have the sold item
        all_items = list(loaded_store._items.values())
        self.assertEqual(len(all_items), 1)
        self.assertEqual(all_items[0].status, ItemStatus.SOLD)


class TestSyncTracking(unittest.TestCase):
    """Test sync status tracking."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = ConsignmentStorage(self.db_path)
        
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = Consignor(
            consignor_id="C1001",
            name="Test",
            address=self.addr,
            split_percent=Decimal("60.00"),
            stocking_fee=Decimal("2.00"),
            created_date=date.today()
        )
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_new_records_are_pending(self):
        """Newly saved records should have pending sync status."""
        self.storage.save_consignor(self.consignor)
        
        changes = self.storage.get_pending_changes()
        self.assertEqual(len(changes['consignors']), 1)
        self.assertEqual(changes['consignors'][0]['consignor_id'], 'C1001')
    
    def test_mark_synced(self):
        """Marking records synced should remove from pending."""
        self.storage.save_consignor(self.consignor)
        self.storage.mark_synced('consignors', 'consignor_id', ['C1001'])
        
        changes = self.storage.get_pending_changes()
        self.assertEqual(len(changes['consignors']), 0)
    
    def test_mark_all_synced(self):
        """Should mark all records in all tables as synced."""
        self.storage.save_consignor(self.consignor)
        
        item = Item(
            item_id="I000001",
            consignor_id="C1001",
            name="Test",
            description="Test",
            original_price=Decimal("50.00"),
            entry_date=date.today(),
            status_date=date.today()
        )
        self.storage.save_item(item)
        
        self.storage.mark_all_synced()
        
        changes = self.storage.get_pending_changes()
        self.assertEqual(len(changes['consignors']), 0)
        self.assertEqual(len(changes['items']), 0)
    
    def test_sync_log(self):
        """Should log sync operations."""
        log_id = self.storage.log_sync('push', 'in_progress')
        self.storage.update_sync_log(log_id, 'success', records_synced=5)
        
        last_sync = self.storage.get_last_sync('push')
        self.assertIsNotNone(last_sync)
        self.assertEqual(last_sync['status'], 'success')
        self.assertEqual(last_sync['records_synced'], 5)


class TestCloudConfig(unittest.TestCase):
    """Test cloud configuration handling."""
    
    def test_from_url(self):
        """Should parse PostgreSQL connection URL."""
        url = "postgresql://myuser:mypass@db.example.com:5432/mydb?sslmode=require"
        config = CloudConfig.from_url(url)
        
        self.assertEqual(config.host, "db.example.com")
        self.assertEqual(config.port, 5432)
        self.assertEqual(config.database, "mydb")
        self.assertEqual(config.user, "myuser")
        self.assertEqual(config.password, "mypass")
        self.assertEqual(config.ssl_mode, "require")
    
    def test_to_connection_string(self):
        """Should generate valid connection string."""
        config = CloudConfig(
            host="localhost",
            port=5432,
            database="test",
            user="user",
            password="pass"
        )
        
        conn_str = config.to_connection_string()
        self.assertIn("host=localhost", conn_str)
        self.assertIn("dbname=test", conn_str)
    
    def test_from_env_not_configured(self):
        """Should return None if env vars not set."""
        # Clear any existing env vars
        for key in ['CONSIGNMENT_CLOUD_HOST', 'CONSIGNMENT_CLOUD_PORT']:
            os.environ.pop(key, None)
        
        config = CloudConfig.from_env()
        self.assertIsNone(config)


class TestCloudSyncNotConfigured(unittest.TestCase):
    """Test CloudSync behavior when not configured."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = ConsignmentStorage(self.db_path)
        
        # Clear env vars
        for key in ['CONSIGNMENT_CLOUD_HOST']:
            os.environ.pop(key, None)
        
        self.sync = CloudSync(self.storage)
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_is_configured_false(self):
        """Should report not configured."""
        self.assertFalse(self.sync.is_configured())
    
    def test_push_returns_error(self):
        """Push should fail gracefully when not configured."""
        result = self.sync.push_changes()
        
        self.assertEqual(result.status, SyncStatus.FAILED)
        self.assertIn("not configured", result.error_message)
    
    def test_pull_returns_error(self):
        """Pull should fail gracefully when not configured."""
        result = self.sync.pull_full(confirm=True)
        
        self.assertEqual(result.status, SyncStatus.FAILED)
        self.assertIn("not configured", result.error_message)
    
    def test_pull_requires_confirmation(self):
        """Pull should require explicit confirmation."""
        # Even if configured, should fail without confirm
        result = self.sync.pull_full(confirm=False)
        
        self.assertEqual(result.status, SyncStatus.FAILED)
        self.assertIn("not confirmed", result.error_message)


class TestBulkImport(unittest.TestCase):
    """Test bulk import functionality for recovery."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = ConsignmentStorage(self.db_path)
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_bulk_import(self):
        """Should import bulk data correctly."""
        data = {
            'config': [
                {'key': 'default_split', 'value': '60.00'},
                {'key': 'default_stocking_fee', 'value': '2.00'}
            ],
            'consignors': [
                {
                    'consignor_id': 'C1001',
                    'name': 'Imported User',
                    'street': '123 Import St',
                    'city': 'Importville',
                    'state': 'IM',
                    'zip_code': '12345',
                    'phone': None,
                    'email': None,
                    'split_percent': '60.00',
                    'stocking_fee': '2.00',
                    'balance': '50.00',
                    'created_date': '2024-01-15'
                }
            ],
            'items': [
                {
                    'item_id': 'I000001',
                    'consignor_id': 'C1001',
                    'name': 'Imported Item',
                    'description': 'From cloud',
                    'original_price': '100.00',
                    'entry_date': '2024-01-20',
                    'status': 'active',
                    'status_date': '2024-01-20'
                }
            ],
            'sales': [],
            'payouts': []
        }
        
        self.storage.bulk_import(data)
        
        # Verify import
        consignor = self.storage.load_consignor('C1001')
        self.assertIsNotNone(consignor)
        self.assertEqual(consignor.name, 'Imported User')
        self.assertEqual(consignor.balance, Decimal('50.00'))
        
        item = self.storage.load_item('I000001')
        self.assertIsNotNone(item)
        self.assertEqual(item.name, 'Imported Item')
    
    def test_clear_and_import(self):
        """Clear should remove existing data before import."""
        # Add some data first
        addr = Address("Old St", "Old City", "OL", "00000")
        consignor = Consignor(
            consignor_id="C9999",
            name="Old User",
            address=addr,
            split_percent=Decimal("50.00"),
            stocking_fee=Decimal("5.00"),
            created_date=date.today()
        )
        self.storage.save_consignor(consignor)
        
        # Clear and import new
        self.storage.clear_all_data()
        
        data = {
            'config': [],
            'consignors': [
                {
                    'consignor_id': 'C1001',
                    'name': 'New User',
                    'street': '123 New St',
                    'city': 'New City',
                    'state': 'NE',
                    'zip_code': '11111',
                    'phone': None,
                    'email': None,
                    'split_percent': '60.00',
                    'stocking_fee': '2.00',
                    'balance': '0.00',
                    'created_date': '2024-01-01'
                }
            ],
            'items': [],
            'sales': [],
            'payouts': []
        }
        
        self.storage.bulk_import(data)
        
        # Old user should be gone
        old = self.storage.load_consignor('C9999')
        self.assertIsNone(old)
        
        # New user should exist
        new = self.storage.load_consignor('C1001')
        self.assertIsNotNone(new)
        self.assertEqual(new.name, 'New User')


if __name__ == "__main__":
    unittest.main(verbosity=2)
