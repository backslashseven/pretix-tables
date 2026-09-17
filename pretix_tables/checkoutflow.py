from django.utils.functional import cached_property
from django.utils.translation import get_language, pgettext_lazy

from pretix.base.timemachine import time_machine_now
from pretix.base.views.tasks import AsyncAction
from pretix.presale.checkoutflow import TemplateFlowStep
from pretix.presale.views import CartMixin, get_cart
from pretix.presale.views.cart import get_or_create_cart_id

from .models import Table
from .tasks import set_cart_tables


class TablesStep(CartMixin, AsyncAction, TemplateFlowStep):
    priority = 38  # before AddOnsStep (40), so table/seat cart positions already exist
                    # by the time AddOnsStep evaluates whether it has anything to show
    identifier = "tables"
    template_name = "pretix_tables/checkout_tables.html"
    task = set_cart_tables
    known_errortypes = ['CartError']
    requires_valid_cart = False
    label = pgettext_lazy('checkoutflow', 'Tables & seats')
    icon = 'th-large'

    @cached_property
    def tables(self):
        return list(
            Table.objects.filter(event=self.event, active=True)
            .select_related('table_item', 'seat_item', 'table_quota', 'seats_quota')
            .order_by('position', 'pk')
        )

    def is_applicable(self, request):
        self.request = request
        # Subevents (event series) are not supported by this plugin yet - never show the
        # step there rather than risk breaking the cart-add call, which requires a subevent.
        if request.event.has_subevents:
            return False
        return len(self.tables) > 0

    def is_completed(self, request, warn=False):
        return bool(self.cart_session.get('tables_step_done'))

    @staticmethod
    def _table_availability(table):
        table_free = table.table_quota.availability()[1] or 0
        seats_free = table.seats_quota.availability()[1] or 0
        return {
            'table': table,
            'seats_free': seats_free,
            'whole_table_available': table_free >= 1 and seats_free >= table.seat_count,
            'max_individual_seats': seats_free,
        }

    def _current_selection(self, request):
        """Maps Table.pk -> {'mode': 'table'} or {'mode': 'seats', 'count': N} based on
        what is currently (still) in the customer's cart."""
        cart = list(get_cart(request).filter(addon_to__isnull=True))
        selection = {}
        for table in self.tables:
            if any(cp.item_id == table.table_item_id for cp in cart):
                selection[table.pk] = {'mode': 'table'}
                continue
            seat_count = sum(1 for cp in cart if cp.item_id == table.seat_item_id)
            if seat_count:
                selection[table.pk] = {'mode': 'seats', 'count': seat_count}
        return selection

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        selection = self._current_selection(self.request)
        rows = []
        for table in self.tables:
            row = self._table_availability(table)
            sel = selection.get(table.pk, {})
            row['selected_mode'] = sel.get('mode', 'none')
            row['selected_seats'] = sel.get('count', 0)
            rows.append(row)
        ctx['tables'] = rows
        ctx['cart'] = self.get_cart()
        return ctx

    def get(self, request):
        self.request = request
        if 'async_id' in request.GET:
            return self.get_result(request)
        return self.render()

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        return self.get_next_url(self.request)

    def get_error_url(self):
        return self.get_step_url(self.request)

    def post(self, request):
        self.request = request

        selection = {}
        for table in self.tables:
            mode = request.POST.get(f'table_{table.pk}_mode')
            if mode == 'table':
                selection[table.pk] = {'mode': 'table'}
            elif mode == 'seats':
                try:
                    count = int(request.POST.get(f'table_{table.pk}_seats') or '0')
                except ValueError:
                    count = 0
                if count > 0:
                    selection[table.pk] = {'mode': 'seats', 'count': count}

        self.cart_session['tables_step_done'] = True

        return self.do(
            self.request.event.id,
            {str(k): v for k, v in selection.items()},
            get_or_create_cart_id(self.request),
            locale=get_language(),
            sales_channel=request.sales_channel.identifier,
            override_now_dt=time_machine_now(default=None),
        )
