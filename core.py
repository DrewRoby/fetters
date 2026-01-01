"""
Core consignment system module.

Handles items, consignors, sales transactions, and payouts for a
consignment store operation.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
import itertools


class ItemStatus(Enum):
    """Lifecycle status of a consignment item."""
    ACTIVE = "active"
    SOLD = "sold"
    RETURNED = "returned"  # Picked up by consignor
    EXPIRED = "expired"    # Store property after 120 days


@dataclass
class Address:
    """Mailing address for a consignor."""
    street: str
    city: str
    state: str
    zip_code: str

    def __str__(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"


@dataclass
class SaleRecord:
    """Record of a completed sale transaction."""
    item_id: str
    sale_date: date
    original_price: Decimal
    sale_price: Decimal
    discount_percent: int
    stocking_fee: Decimal
    consignor_share: Decimal
    store_share: Decimal

    def __post_init__(self):
        # Ensure all money fields are Decimal
        self.original_price = Decimal(str(self.original_price))
        self.sale_price = Decimal(str(self.sale_price))
        self.stocking_fee = Decimal(str(self.stocking_fee))
        self.consignor_share = Decimal(str(self.consignor_share))
        self.store_share = Decimal(str(self.store_share))


@dataclass
class Payout:
    """Record of a payout to a consignor."""
    payout_id: str
    consignor_id: str
    payout_date: date
    amount: Decimal
    check_number: Optional[str] = None

    def __post_init__(self):
        self.amount = Decimal(str(self.amount))


@dataclass
class Item:
    """A consignment item with automatic discount scheduling."""
    item_id: str
    consignor_id: str
    name: str
    description: str
    original_price: Decimal
    entry_date: date
    status: ItemStatus = ItemStatus.ACTIVE
    sale_record: Optional[SaleRecord] = None
    status_date: date = field(default_factory=date.today)  # When status last changed

    # Discount schedule: (days_threshold, discount_percentage)
    DISCOUNT_SCHEDULE = [
        (90, 75),
        (60, 50),
        (30, 25),
        (0, 0),
    ]
    EXPIRY_DAYS = 120

    def __post_init__(self):
        self.original_price = Decimal(str(self.original_price))
        if self.status_date is None:
            self.status_date = self.entry_date

    def days_since_entry(self, as_of: Optional[date] = None) -> int:
        """Calculate days since item was entered."""
        check_date = as_of or date.today()
        return (check_date - self.entry_date).days

    def discount_percent(self, as_of: Optional[date] = None) -> int:
        """Get current discount percentage based on age."""
        days = self.days_since_entry(as_of)
        for threshold, discount in self.DISCOUNT_SCHEDULE:
            if days >= threshold:
                return discount
        return 0

    def current_price(self, as_of: Optional[date] = None) -> Decimal:
        """Calculate current price after time-based discount."""
        discount = self.discount_percent(as_of)
        multiplier = Decimal(str(100 - discount)) / Decimal("100")
        price = self.original_price * multiplier
        return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def is_expired(self, as_of: Optional[date] = None) -> bool:
        """Check if item has passed the 120-day expiry threshold."""
        return self.days_since_entry(as_of) >= self.EXPIRY_DAYS

    def price_tier_description(self, as_of: Optional[date] = None) -> str:
        """Human-readable description of current pricing tier."""
        days = self.days_since_entry(as_of)
        discount = self.discount_percent(as_of)

        if days >= self.EXPIRY_DAYS:
            return "Expired - Store Property"
        elif discount == 0:
            return "Full Price"
        else:
            return f"{discount}% Off"


@dataclass
class Consignor:
    """A consignor (client) who provides items for sale."""
    consignor_id: str
    name: str
    address: Address
    split_percent: Decimal  # Consignor's percentage of sale (after stocking fee)
    stocking_fee: Decimal   # Flat fee per item sold
    balance: Decimal = Decimal("0.00")
    phone: Optional[str] = None
    email: Optional[str] = None
    created_date: date = field(default_factory=date.today)

    def __post_init__(self):
        self.split_percent = Decimal(str(self.split_percent))
        self.stocking_fee = Decimal(str(self.stocking_fee))
        self.balance = Decimal(str(self.balance))


class ConsignmentStore:
    """
    Main consignment store management system.

    Handles consignor accounts, item inventory, sales, and payouts.
    """

    # Default terms for new consignors
    DEFAULT_CONSIGNOR_SPLIT = Decimal("60.00")  # 60% to consignor
    DEFAULT_STOCKING_FEE = Decimal("2.00")       # $2 per item

    def __init__(
            self,
            default_split: Optional[Decimal] = None,
            default_stocking_fee: Optional[Decimal] = None
    ):
        self.default_split = Decimal(str(default_split or self.DEFAULT_CONSIGNOR_SPLIT))
        self.default_stocking_fee = Decimal(str(default_stocking_fee or self.DEFAULT_STOCKING_FEE))

        self._consignors: dict[str, Consignor] = {}
        self._items: dict[str, Item] = {}
        self._payouts: list[Payout] = []

        # ID generators
        self._consignor_counter = itertools.count(1001)
        self._item_counter = itertools.count(1)
        self._payout_counter = itertools.count(1)

    # --- Consignor Management ---

    def add_consignor(
            self,
            name: str,
            address: Address,
            split_percent: Optional[Decimal] = None,
            stocking_fee: Optional[Decimal] = None,
            phone: Optional[str] = None,
            email: Optional[str] = None
    ) -> Consignor:
        """Register a new consignor with the store."""
        consignor_id = f"C{next(self._consignor_counter)}"

        consignor = Consignor(
            consignor_id=consignor_id,
            name=name,
            address=address,
            split_percent=split_percent if split_percent is not None else self.default_split,
            stocking_fee=stocking_fee if stocking_fee is not None else self.default_stocking_fee,
            phone=phone,
            email=email
        )

        self._consignors[consignor_id] = consignor
        return consignor

    def get_consignor(self, consignor_id: str) -> Optional[Consignor]:
        """Retrieve a consignor by ID."""
        return self._consignors.get(consignor_id)

    def update_consignor_terms(
            self,
            consignor_id: str,
            split_percent: Optional[Decimal] = None,
            stocking_fee: Optional[Decimal] = None
    ) -> Consignor:
        """Update a consignor's commission terms."""
        consignor = self._consignors.get(consignor_id)
        if not consignor:
            raise ValueError(f"Consignor {consignor_id} not found")

        if split_percent is not None:
            consignor.split_percent = Decimal(str(split_percent))
        if stocking_fee is not None:
            consignor.stocking_fee = Decimal(str(stocking_fee))

        return consignor

    def list_consignors(self) -> list[Consignor]:
        """List all consignors."""
        return list(self._consignors.values())

    # --- Item Management ---

    def add_item(
            self,
            consignor_id: str,
            name: str,
            description: str,
            price: Decimal,
            entry_date: Optional[date] = None
    ) -> Item:
        """Add a new item to consignment inventory."""
        if consignor_id not in self._consignors:
            raise ValueError(f"Consignor {consignor_id} not found")

        item_id = f"I{next(self._item_counter):06d}"

        item = Item(
            item_id=item_id,
            consignor_id=consignor_id,
            name=name,
            description=description,
            original_price=Decimal(str(price)),
            entry_date=entry_date or date.today()
        )

        self._items[item_id] = item
        return item

    def get_item(self, item_id: str) -> Optional[Item]:
        """Retrieve an item by ID."""
        return self._items.get(item_id)

    def get_items_by_consignor(
            self,
            consignor_id: str,
            status: Optional[ItemStatus] = None
    ) -> list[Item]:
        """Get all items for a consignor, optionally filtered by status."""
        items = [i for i in self._items.values() if i.consignor_id == consignor_id]
        if status:
            items = [i for i in items if i.status == status]
        return items

    def get_active_items(self) -> list[Item]:
        """Get all active (unsold, not returned) items."""
        return [i for i in self._items.values() if i.status == ItemStatus.ACTIVE]

    def get_expiring_items(self, within_days: int = 14) -> list[Item]:
        """Get active items that will expire within the specified days."""
        cutoff = Item.EXPIRY_DAYS - within_days
        return [
            i for i in self._items.values()
            if i.status == ItemStatus.ACTIVE
               and cutoff <= i.days_since_entry() < Item.EXPIRY_DAYS
        ]

    # --- Sales ---

    def sell_item(
            self,
            item_id: str,
            sale_date: Optional[date] = None
    ) -> SaleRecord:
        """
        Process the sale of an item.

        Calculates split based on the consignor's terms, updates item status,
        and credits the consignor's balance.
        """
        item = self._items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found")
        if item.status != ItemStatus.ACTIVE:
            raise ValueError(f"Item {item_id} is not active (status: {item.status.value})")

        sale_date = sale_date or date.today()
        consignor = self._consignors[item.consignor_id]

        # Calculate sale price with discount
        discount = item.discount_percent(sale_date)
        sale_price = item.current_price(sale_date)

        # Calculate split
        # Formula: (sale_price - stocking_fee) * consignor_percent = consignor_share
        # Store gets: stocking_fee + (sale_price - stocking_fee) * (1 - consignor_percent)
        stocking_fee = consignor.stocking_fee
        net_after_fee = sale_price - stocking_fee

        consignor_rate = consignor.split_percent / Decimal("100")
        consignor_share = (net_after_fee * consignor_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        store_share = sale_price - consignor_share  # Store gets fee + their split

        # Ensure consignor share isn't negative if stocking fee > sale price
        if consignor_share < 0:
            consignor_share = Decimal("0.00")
            store_share = sale_price

        sale_record = SaleRecord(
            item_id=item_id,
            sale_date=sale_date,
            original_price=item.original_price,
            sale_price=sale_price,
            discount_percent=discount,
            stocking_fee=stocking_fee,
            consignor_share=consignor_share,
            store_share=store_share
        )

        # Update item
        item.status = ItemStatus.SOLD
        item.status_date = sale_date
        item.sale_record = sale_record

        # Credit consignor
        consignor.balance += consignor_share

        return sale_record

    def return_item_to_consignor(
            self,
            item_id: str,
            return_date: Optional[date] = None
    ) -> Item:
        """Mark an item as returned to/picked up by the consignor."""
        item = self._items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found")
        if item.status != ItemStatus.ACTIVE:
            raise ValueError(f"Item {item_id} is not active (status: {item.status.value})")

        item.status = ItemStatus.RETURNED
        item.status_date = return_date or date.today()
        return item

    def expire_item(self, item_id: str, expire_date: Optional[date] = None) -> Item:
        """Mark an item as expired (store property)."""
        item = self._items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found")
        if item.status != ItemStatus.ACTIVE:
            raise ValueError(f"Item {item_id} is not active (status: {item.status.value})")

        item.status = ItemStatus.EXPIRED
        item.status_date = expire_date or date.today()
        return item

    def process_expirations(self, as_of: Optional[date] = None) -> list[Item]:
        """
        Check all active items and mark any that have reached 120 days as expired.

        Returns list of newly expired items.
        """
        check_date = as_of or date.today()
        expired = []

        for item in self._items.values():
            if item.status == ItemStatus.ACTIVE and item.is_expired(check_date):
                item.status = ItemStatus.EXPIRED
                item.status_date = check_date
                expired.append(item)

        return expired

    # --- Payouts ---

    def process_payout(
            self,
            consignor_id: str,
            check_number: Optional[str] = None,
            payout_date: Optional[date] = None
    ) -> Optional[Payout]:
        """
        Pay out a consignor's full balance.

        Returns None if balance is zero.
        """
        consignor = self._consignors.get(consignor_id)
        if not consignor:
            raise ValueError(f"Consignor {consignor_id} not found")

        if consignor.balance <= 0:
            return None

        payout_id = f"P{next(self._payout_counter):06d}"
        payout = Payout(
            payout_id=payout_id,
            consignor_id=consignor_id,
            payout_date=payout_date or date.today(),
            amount=consignor.balance,
            check_number=check_number
        )

        consignor.balance = Decimal("0.00")
        self._payouts.append(payout)

        return payout

    def get_payout_history(self, consignor_id: Optional[str] = None) -> list[Payout]:
        """Get payout history, optionally filtered by consignor."""
        if consignor_id:
            return [p for p in self._payouts if p.consignor_id == consignor_id]
        return list(self._payouts)

    # --- Reporting Helpers (for future expansion) ---

    def get_sales_for_consignor(self, consignor_id: str) -> list[SaleRecord]:
        """Get all sale records for a consignor."""
        return [
            item.sale_record
            for item in self._items.values()
            if item.consignor_id == consignor_id and item.sale_record
        ]

    def get_inventory_summary(self) -> dict:
        """Get summary counts of inventory by status."""
        summary = {status: 0 for status in ItemStatus}
        for item in self._items.values():
            summary[item.status] += 1
        return summary