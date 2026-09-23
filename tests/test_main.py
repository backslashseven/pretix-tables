from decimal import Decimal

import pytest
from django_scopes import scopes_disabled

from pretix.base.models import CartPosition
from pretix.base.services.cart import CartError, CartManager
from pretix.presale.productlist import item_group_by_category

from pretix_tables.models import Table


@pytest.fixture
@scopes_disabled()
def category(event):
    return event.categories.create(name="Regular products", position=0)


@pytest.fixture
@scopes_disabled()
def table(event):
    t = Table.objects.create(
        event=event, name="Table 1", seat_count=2,
        table_price=Decimal('10.00'), seat_price=Decimal('5.00'),
    )
    t.sync_pretix_objects()
    return t


@pytest.fixture
@scopes_disabled()
def cart_manager(event):
    return CartManager(
        event=event, cart_id='tables-test-cart',
        sales_channel=event.organizer.sales_channels.get(identifier='web'),
    )


@pytest.mark.django_db
@scopes_disabled()
def test_table_items_get_a_dedicated_category(table):
    assert table.table_item.category_id is not None
    assert table.table_item.category_id == table.seat_item.category_id


@pytest.mark.django_db
@scopes_disabled()
def test_tables_category_sorts_after_existing_categories(event, category, table):
    regular_item = event.items.create(name="Regular product", default_price=1, category=category)
    tables_category = table.table_item.category

    assert tables_category.position > category.position

    groups = item_group_by_category([regular_item, table.table_item])
    assert [g[0] for g in groups] == [category, tables_category]


@pytest.mark.django_db
@scopes_disabled()
def test_tables_category_stays_pinned_after_reordering(event, category, table, django_capture_on_commit_callbacks):
    tables_category = table.table_item.category
    # Start it out of place - if the post_save signal in signals.py didn't run the pin,
    # this position would simply survive the reorder below and the assertion would fail.
    tables_category.position = 0
    tables_category.save(update_fields=['position'])
    category.position = 1
    category.save(update_fields=['position'])

    # Simulate pretix core's reorder_categories() view dragging another category into place -
    # its per-category .save() calls are what fire pin_tables_category_last().
    with django_capture_on_commit_callbacks(execute=True):
        other = event.categories.create(name="Another category", position=2)

    tables_category.refresh_from_db()
    assert tables_category.position > other.position
    assert tables_category.position > category.position


@pytest.mark.django_db
@scopes_disabled()
def test_seat_item_is_bundle_only(table):
    assert table.seat_item.require_bundling is True


@pytest.mark.django_db
@scopes_disabled()
def test_seat_cannot_be_booked_on_its_own(table, cart_manager):
    seat_variation = table.seat_item.variations.get(position=0)

    with pytest.raises(CartError):
        cart_manager.add_new_items([
            {'item': table.seat_item.pk, 'variation': seat_variation.pk, 'count': 1},
        ])

    assert not CartPosition.objects.filter(event=table.event).exists()


@pytest.mark.django_db
@scopes_disabled()
def test_booking_table_adds_one_seat_position_per_seat(table, cart_manager):
    cart_manager.add_new_items([
        {'item': table.table_item.pk, 'variation': None, 'count': 1},
    ])
    cart_manager.commit()

    table_position = CartPosition.objects.get(event=table.event, item=table.table_item)
    seat_positions = table_position.addons.filter(item=table.seat_item)

    assert seat_positions.count() == table.seat_count
    assert all(seat_positions.values_list('is_bundled', flat=True))
    assert {p.variation_id for p in seat_positions} == set(
        table.seat_item.variations.values_list('pk', flat=True)
    )


@pytest.mark.django_db
@scopes_disabled()
def test_sync_repairs_seat_whose_variation_was_deleted_elsewhere(table):
    # Simulate an ItemVariation being deleted outside the plugin (e.g. through pretix core's
    # own product admin) - this SET_NULLs TableSeat.variation/quota but leaves the TableSeat
    # row itself in place, which is what crashed sync_pretix_objects() in production.
    seat = table.table_seats.get(seat_number=1)
    orphaned_variation_id = seat.variation_id
    seat.variation.delete()
    seat.quota.delete()
    seat.refresh_from_db()
    assert seat.variation_id is None
    assert seat.quota_id is None

    table.sync_pretix_objects()

    seat.refresh_from_db()
    assert seat.variation_id is not None
    assert seat.variation_id != orphaned_variation_id
    assert seat.quota_id is not None
    assert seat.bundle.bundled_variation_id == seat.variation_id


@pytest.mark.django_db
@scopes_disabled()
def test_sync_is_noop_for_already_synced_seats(table):
    seat = table.table_seats.get(seat_number=1)
    variation_id, quota_id, bundle_id = seat.variation_id, seat.quota_id, seat.bundle_id

    table.sync_pretix_objects()

    seat.refresh_from_db()
    assert (seat.variation_id, seat.quota_id, seat.bundle_id) == (variation_id, quota_id, bundle_id)
