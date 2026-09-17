from datetime import datetime
from typing import Dict, Optional

from celery.exceptions import MaxRetriesExceededError
from django_scopes import scopes_disabled

from pretix.base.i18n import language
from pretix.base.models import Event, SalesChannel
from pretix.base.services.cart import CartError, CartManager, error_messages
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.tasks import ProfiledEventTask
from pretix.base.timemachine import time_machine_now_assigned
from pretix.celery_app import app

from .models import Table


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def set_cart_tables(self, event: Event, selection: Dict[str, dict], cart_id: str = None, locale='en',
                    sales_channel='web', override_now_dt: Optional[datetime] = None) -> None:
    """
    Reconciles a customer's table/seat selection with their cart: removes any previously
    booked table/seat cart positions and adds back exactly the newly selected ones, all
    through pretix's normal CartManager so quota checks and locking apply as usual.

    :param event: The event in question
    :param selection: A dict mapping Table id (as str, due to task serialization) to either
                      {'mode': 'table'} or {'mode': 'seats', 'count': N}
    :param cart_id: The cart ID of the cart to modify
    """
    with language(locale), time_machine_now_assigned(override_now_dt):
        selection = {int(k): v for k, v in (selection or {}).items()}

        try:
            sales_channel = event.organizer.sales_channels.get(identifier=sales_channel)
        except SalesChannel.DoesNotExist:
            raise CartError("Invalid sales channel.")

        with scopes_disabled():
            tables = list(Table.objects.filter(event=event, active=True))

        try:
            try:
                cm = CartManager(event=event, cart_id=cart_id, sales_channel=sales_channel)

                relevant_items = [t.table_item_id for t in tables] + [t.seat_item_id for t in tables]
                for cp in cm.positions.filter(addon_to__isnull=True, item_id__in=relevant_items):
                    cm.remove_item(cp.pk)

                items = []
                for table in tables:
                    sel = selection.get(table.pk)
                    if not sel:
                        continue
                    if sel.get('mode') == 'table':
                        items.append({'item': table.table_item_id, 'variation': None, 'count': 1})
                    elif sel.get('mode') == 'seats' and int(sel.get('count') or 0) > 0:
                        items.append({
                            'item': table.seat_item_id, 'variation': None, 'count': int(sel['count']),
                        })

                if items:
                    cm.add_new_items(items)
                cm.commit()
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise CartError(error_messages['busy'])
