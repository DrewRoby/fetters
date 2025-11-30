"""
Tests for the consignment core module.
Uses standard library unittest (no external dependencies).
"""

import unittest
from datetime import date, timedelta
from decimal import Decimal

from core import (
    ItemStatus, Address, SaleRecord, Payout, Item, Consignor,
    ConsignmentStore
)


class TestAddress(unittest.TestCase):
    def test_str_format(self):
        addr = Address(
            street="123 Main St",
            city="Springfield",
            state="IL",
            zip_code="62701"
        )
        self.assertEqual(str(addr), "123 Main St, Springfield, IL 62701")


class TestItem(unittest.TestCase):
    def make_item(self, entry_date=None, price="100.00"):
        return Item(
            item_id="I000001",
            consignor_id="C1001",
            name="Test Item",
            description="Test description",
            original_price=Decimal(price),
            entry_date=entry_date or date.today()
        )

    def test_creation(self):
        item = self.make_item(price="50.00")
        self.assertEqual(item.status, ItemStatus.ACTIVE)
        self.assertEqual(item.original_price, Decimal("50.00"))

    def test_days_since_entry(self):
        entry = date.today() - timedelta(days=45)
        item = self.make_item(entry_date=entry)
        self.assertEqual(item.days_since_entry(), 45)

    def test_discount_schedule_day_0(self):
        """Items on entry date should be full price."""
        item = self.make_item()
        self.assertEqual(item.discount_percent(), 0)
        self.assertEqual(item.current_price(), Decimal("100.00"))

    def test_discount_schedule_day_29(self):
        """Day 29 should still be full price."""
        entry = date.today() - timedelta(days=29)
        item = self.make_item(entry_date=entry)
        self.assertEqual(item.discount_percent(), 0)
        self.assertEqual(item.current_price(), Decimal("100.00"))

    def test_discount_schedule_day_30(self):
        """Day 30 should be 25% off."""
        entry = date.today() - timedelta(days=30)
        item = self.make_item(entry_date=entry)
        self.assertEqual(item.discount_percent(), 25)
        self.assertEqual(item.current_price(), Decimal("75.00"))

    def test_discount_schedule_day_60(self):
        """Day 60 should be 50% off."""
        entry = date.today() - timedelta(days=60)
        item = self.make_item(entry_date=entry)
        self.assertEqual(item.discount_percent(), 50)
        self.assertEqual(item.current_price(), Decimal("50.00"))

    def test_discount_schedule_day_90(self):
        """Day 90 should be 75% off."""
        entry = date.today() - timedelta(days=90)
        item = self.make_item(entry_date=entry)
        self.assertEqual(item.discount_percent(), 75)
        self.assertEqual(item.current_price(), Decimal("25.00"))

    def test_is_expired_before_120(self):
        """Item at 119 days should not be expired."""
        entry = date.today() - timedelta(days=119)
        item = self.make_item(entry_date=entry)
        self.assertFalse(item.is_expired())

    def test_is_expired_at_120(self):
        """Item at 120 days should be expired."""
        entry = date.today() - timedelta(days=120)
        item = self.make_item(entry_date=entry)
        self.assertTrue(item.is_expired())

    def test_price_tier_description(self):
        item = self.make_item()
        self.assertEqual(item.price_tier_description(), "Full Price")

        item.entry_date = date.today() - timedelta(days=30)
        self.assertEqual(item.price_tier_description(), "25% Off")

        item.entry_date = date.today() - timedelta(days=120)
        self.assertEqual(item.price_tier_description(), "Expired - Store Property")

    def test_discount_with_specific_date(self):
        """Test discount calculation with a specific as_of date."""
        entry = date(2024, 1, 1)
        item = self.make_item(entry_date=entry)

        # Check price at day 0
        self.assertEqual(item.current_price(as_of=date(2024, 1, 1)), Decimal("100.00"))
        # Check price at day 30
        self.assertEqual(item.current_price(as_of=date(2024, 1, 31)), Decimal("75.00"))
        # Check price at day 60
        self.assertEqual(item.current_price(as_of=date(2024, 3, 1)), Decimal("50.00"))


class TestConsignor(unittest.TestCase):
    def test_creation(self):
        addr = Address("123 Main", "City", "ST", "12345")
        consignor = Consignor(
            consignor_id="C1001",
            name="John Smith",
            address=addr,
            split_percent=Decimal("60.00"),
            stocking_fee=Decimal("2.00")
        )
        self.assertEqual(consignor.balance, Decimal("0.00"))
        self.assertEqual(consignor.split_percent, Decimal("60.00"))


class TestStoreBasics(unittest.TestCase):
    def test_default_terms(self):
        store = ConsignmentStore()
        self.assertEqual(store.default_split, Decimal("60.00"))
        self.assertEqual(store.default_stocking_fee, Decimal("2.00"))

    def test_custom_default_terms(self):
        store = ConsignmentStore(
            default_split=Decimal("55.00"),
            default_stocking_fee=Decimal("3.50")
        )
        self.assertEqual(store.default_split, Decimal("55.00"))
        self.assertEqual(store.default_stocking_fee, Decimal("3.50"))


class TestConsignorManagement(unittest.TestCase):
    def setUp(self):
        self.store = ConsignmentStore()
        self.addr = Address("123 Main", "City", "ST", "12345")

    def test_add_consignor_with_defaults(self):
        consignor = self.store.add_consignor(name="Jane Doe", address=self.addr)
        self.assertTrue(consignor.consignor_id.startswith("C"))
        self.assertEqual(consignor.split_percent, Decimal("60.00"))
        self.assertEqual(consignor.stocking_fee, Decimal("2.00"))

    def test_add_consignor_custom_terms(self):
        consignor = self.store.add_consignor(
            name="VIP Client",
            address=self.addr,
            split_percent=Decimal("70.00"),
            stocking_fee=Decimal("1.00")
        )
        self.assertEqual(consignor.split_percent, Decimal("70.00"))
        self.assertEqual(consignor.stocking_fee, Decimal("1.00"))

    def test_get_consignor(self):
        added = self.store.add_consignor(name="Test", address=self.addr)
        retrieved = self.store.get_consignor(added.consignor_id)
        self.assertIs(retrieved, added)

    def test_get_consignor_not_found(self):
        self.assertIsNone(self.store.get_consignor("NONEXISTENT"))

    def test_update_consignor_terms(self):
        consignor = self.store.add_consignor(name="Test", address=self.addr)
        self.store.update_consignor_terms(
            consignor.consignor_id,
            split_percent=Decimal("65.00")
        )
        self.assertEqual(consignor.split_percent, Decimal("65.00"))
        self.assertEqual(consignor.stocking_fee, Decimal("2.00"))  # Unchanged

    def test_list_consignors(self):
        self.store.add_consignor(name="First", address=self.addr)
        self.store.add_consignor(name="Second", address=self.addr)
        consignors = self.store.list_consignors()
        self.assertEqual(len(consignors), 2)


class TestItemManagement(unittest.TestCase):
    def setUp(self):
        self.store = ConsignmentStore()
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = self.store.add_consignor(name="Test", address=self.addr)

    def test_add_item(self):
        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Antique Vase",
            description="Blue china vase, circa 1920",
            price=Decimal("75.00")
        )
        self.assertTrue(item.item_id.startswith("I"))
        self.assertEqual(item.status, ItemStatus.ACTIVE)
        self.assertEqual(item.original_price, Decimal("75.00"))

    def test_add_item_invalid_consignor(self):
        with self.assertRaises(ValueError):
            self.store.add_item(
                consignor_id="INVALID",
                name="Test",
                description="Test",
                price=Decimal("10.00")
            )

    def test_get_item(self):
        added = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Test",
            description="Test",
            price=Decimal("50.00")
        )
        retrieved = self.store.get_item(added.item_id)
        self.assertIs(retrieved, added)

    def test_get_items_by_consignor(self):
        self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Item 1",
            description="Desc",
            price=Decimal("10.00")
        )
        self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Item 2",
            description="Desc",
            price=Decimal("20.00")
        )
        items = self.store.get_items_by_consignor(self.consignor.consignor_id)
        self.assertEqual(len(items), 2)

    def test_get_active_items(self):
        item1 = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Active",
            description="Desc",
            price=Decimal("10.00")
        )
        item2 = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Will be sold",
            description="Desc",
            price=Decimal("20.00")
        )
        self.store.sell_item(item2.item_id)

        active = self.store.get_active_items()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].item_id, item1.item_id)


class TestSales(unittest.TestCase):
    def setUp(self):
        self.store = ConsignmentStore()
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = self.store.add_consignor(name="Test", address=self.addr)

    def test_sell_item_basic(self):
        """Test basic sale with default 60/40 split and $2 stocking fee."""
        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Widget",
            description="A widget",
            price=Decimal("100.00")
        )

        sale = self.store.sell_item(item.item_id)

        # Sale price at full price = $100
        self.assertEqual(sale.sale_price, Decimal("100.00"))
        self.assertEqual(sale.discount_percent, 0)
        self.assertEqual(sale.stocking_fee, Decimal("2.00"))

        # Split: ($100 - $2) * 60% = $58.80 to consignor
        self.assertEqual(sale.consignor_share, Decimal("58.80"))
        # Store gets: $100 - $58.80 = $41.20
        self.assertEqual(sale.store_share, Decimal("41.20"))

        # Item status updated
        self.assertEqual(item.status, ItemStatus.SOLD)
        self.assertIs(item.sale_record, sale)

        # Consignor balance credited
        self.assertEqual(self.consignor.balance, Decimal("58.80"))

    def test_sell_item_with_discount(self):
        """Test sale of an item that's been in store 30+ days."""
        entry_date = date.today() - timedelta(days=35)

        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Old Widget",
            description="Widget",
            price=Decimal("100.00"),
            entry_date=entry_date
        )

        sale = self.store.sell_item(item.item_id)

        # 25% off: $100 * 0.75 = $75
        self.assertEqual(sale.sale_price, Decimal("75.00"))
        self.assertEqual(sale.discount_percent, 25)

        # Split: ($75 - $2) * 60% = $43.80
        self.assertEqual(sale.consignor_share, Decimal("43.80"))

    def test_sell_item_custom_terms(self):
        """Test sale with custom consignor terms."""
        premium_consignor = self.store.add_consignor(
            name="Premium Seller",
            address=self.addr,
            split_percent=Decimal("70.00"),
            stocking_fee=Decimal("1.00")
        )
        item = self.store.add_item(
            consignor_id=premium_consignor.consignor_id,
            name="Premium Item",
            description="Fancy",
            price=Decimal("100.00")
        )

        sale = self.store.sell_item(item.item_id)

        # Split: ($100 - $1) * 70% = $69.30
        self.assertEqual(sale.consignor_share, Decimal("69.30"))
        self.assertEqual(sale.store_share, Decimal("30.70"))

    def test_sell_item_not_found(self):
        with self.assertRaises(ValueError):
            self.store.sell_item("INVALID")

    def test_sell_item_already_sold(self):
        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Test",
            description="Test",
            price=Decimal("50.00")
        )
        self.store.sell_item(item.item_id)

        with self.assertRaises(ValueError):
            self.store.sell_item(item.item_id)

    def test_sell_cheap_item_stocking_fee_exceeds(self):
        """If stocking fee exceeds sale price, consignor gets $0."""
        entry_date = date.today() - timedelta(days=90)

        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Cheap Thing",
            description="Very cheap",
            price=Decimal("5.00"),  # At 75% off = $1.25
            entry_date=entry_date
        )

        sale = self.store.sell_item(item.item_id)

        # Consignor share can't go negative
        self.assertEqual(sale.consignor_share, Decimal("0.00"))
        self.assertEqual(sale.store_share, Decimal("1.25"))


class TestReturns(unittest.TestCase):
    def setUp(self):
        self.store = ConsignmentStore()
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = self.store.add_consignor(name="Test", address=self.addr)

    def test_return_item(self):
        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Test",
            description="Test",
            price=Decimal("50.00")
        )

        returned = self.store.return_item_to_consignor(item.item_id)

        self.assertEqual(returned.status, ItemStatus.RETURNED)
        self.assertIs(returned, item)

    def test_return_sold_item_fails(self):
        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Test",
            description="Test",
            price=Decimal("50.00")
        )
        self.store.sell_item(item.item_id)

        with self.assertRaises(ValueError):
            self.store.return_item_to_consignor(item.item_id)


class TestExpiration(unittest.TestCase):
    def setUp(self):
        self.store = ConsignmentStore()
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = self.store.add_consignor(name="Test", address=self.addr)

    def test_expire_item_manually(self):
        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Test",
            description="Test",
            price=Decimal("50.00")
        )

        self.store.expire_item(item.item_id)
        self.assertEqual(item.status, ItemStatus.EXPIRED)

    def test_process_expirations(self):
        # Add old item (should expire)
        old_item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Old",
            description="Old item",
            price=Decimal("50.00"),
            entry_date=date.today() - timedelta(days=125)
        )

        # Add new item (should not expire)
        new_item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="New",
            description="New item",
            price=Decimal("50.00")
        )

        expired = self.store.process_expirations()

        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].item_id, old_item.item_id)
        self.assertEqual(old_item.status, ItemStatus.EXPIRED)
        self.assertEqual(new_item.status, ItemStatus.ACTIVE)

    def test_get_expiring_items(self):
        # Item expiring in 10 days (at day 110)
        expiring_soon = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Expiring Soon",
            description="Desc",
            price=Decimal("50.00"),
            entry_date=date.today() - timedelta(days=110)
        )

        # Item not expiring soon (at day 50)
        not_expiring = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Not Expiring",
            description="Desc",
            price=Decimal("50.00"),
            entry_date=date.today() - timedelta(days=50)
        )

        expiring = self.store.get_expiring_items(within_days=14)

        self.assertEqual(len(expiring), 1)
        self.assertEqual(expiring[0].item_id, expiring_soon.item_id)


class TestPayouts(unittest.TestCase):
    def setUp(self):
        self.store = ConsignmentStore()
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = self.store.add_consignor(name="Test", address=self.addr)

    def test_process_payout(self):
        # Make some sales to build up balance
        item = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Test",
            description="Test",
            price=Decimal("100.00")
        )
        self.store.sell_item(item.item_id)

        self.assertEqual(self.consignor.balance, Decimal("58.80"))

        payout = self.store.process_payout(
            self.consignor.consignor_id,
            check_number="1001"
        )

        self.assertEqual(payout.amount, Decimal("58.80"))
        self.assertEqual(payout.check_number, "1001")
        self.assertEqual(self.consignor.balance, Decimal("0.00"))

    def test_payout_zero_balance(self):
        payout = self.store.process_payout(self.consignor.consignor_id)
        self.assertIsNone(payout)

    def test_payout_history(self):
        # Build balance and pay out twice
        for i in range(2):
            item = self.store.add_item(
                consignor_id=self.consignor.consignor_id,
                name=f"Item {i}",
                description="Test",
                price=Decimal("100.00")
            )
            self.store.sell_item(item.item_id)
            self.store.process_payout(
                self.consignor.consignor_id,
                check_number=f"100{i}"
            )

        history = self.store.get_payout_history(self.consignor.consignor_id)
        self.assertEqual(len(history), 2)


class TestReporting(unittest.TestCase):
    def setUp(self):
        self.store = ConsignmentStore()
        self.addr = Address("123 Main", "City", "ST", "12345")
        self.consignor = self.store.add_consignor(name="Test", address=self.addr)

    def test_get_sales_for_consignor(self):
        for i in range(3):
            item = self.store.add_item(
                consignor_id=self.consignor.consignor_id,
                name=f"Item {i}",
                description="Test",
                price=Decimal("50.00")
            )
            self.store.sell_item(item.item_id)

        sales = self.store.get_sales_for_consignor(self.consignor.consignor_id)
        self.assertEqual(len(sales), 3)

    def test_inventory_summary(self):
        # Add various items in different states
        active = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Active",
            description="Test",
            price=Decimal("50.00")
        )

        sold = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Sold",
            description="Test",
            price=Decimal("50.00")
        )
        self.store.sell_item(sold.item_id)

        returned = self.store.add_item(
            consignor_id=self.consignor.consignor_id,
            name="Returned",
            description="Test",
            price=Decimal("50.00")
        )
        self.store.return_item_to_consignor(returned.item_id)

        summary = self.store.get_inventory_summary()

        self.assertEqual(summary[ItemStatus.ACTIVE], 1)
        self.assertEqual(summary[ItemStatus.SOLD], 1)
        self.assertEqual(summary[ItemStatus.RETURNED], 1)
        self.assertEqual(summary[ItemStatus.EXPIRED], 0)


class TestIntegration(unittest.TestCase):
    def test_full_consignment_cycle(self):
        """Test a complete consignment workflow."""
        store = ConsignmentStore()
        addr = Address("456 Oak Ave", "Townsville", "CA", "90210")

        # 1. Register consignor
        consignor = store.add_consignor(
            name="Alice Smith",
            address=addr,
            phone="555-1234",
            email="alice@example.com"
        )

        # 2. Consignor brings in items
        item1 = store.add_item(
            consignor_id=consignor.consignor_id,
            name="Antique Clock",
            description="Victorian mantle clock, working condition",
            price=Decimal("200.00")
        )
        item2 = store.add_item(
            consignor_id=consignor.consignor_id,
            name="Vintage Dress",
            description="1950s cocktail dress, size 8",
            price=Decimal("75.00")
        )
        item3 = store.add_item(
            consignor_id=consignor.consignor_id,
            name="Old Books",
            description="Set of encyclopedias",
            price=Decimal("30.00"),
            entry_date=date.today() - timedelta(days=95)  # About to expire
        )

        # 3. One item sells at full price
        sale1 = store.sell_item(item1.item_id)
        self.assertEqual(sale1.sale_price, Decimal("200.00"))

        # 4. Consignor picks up one item
        store.return_item_to_consignor(item2.item_id)

        # 5. Check expiring items
        expiring = store.get_expiring_items(within_days=30)
        self.assertEqual(len(expiring), 1)
        self.assertEqual(expiring[0].item_id, item3.item_id)

        # 6. Pay out consignor
        payout = store.process_payout(
            consignor.consignor_id,
            check_number="5001"
        )

        # ($200 - $2) * 60% = $118.80
        self.assertEqual(payout.amount, Decimal("118.80"))
        self.assertEqual(consignor.balance, Decimal("0.00"))

        # 7. Verify inventory state
        summary = store.get_inventory_summary()
        self.assertEqual(summary[ItemStatus.ACTIVE], 1)  # Old books still active
        self.assertEqual(summary[ItemStatus.SOLD], 1)
        self.assertEqual(summary[ItemStatus.RETURNED], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)