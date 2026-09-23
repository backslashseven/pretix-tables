from decimal import Decimal

import pytest
from django_scopes import scopes_disabled

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
