from django.db.models import Q
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pretix.control.signals import nav_event, order_info

from .models import Table


@receiver(nav_event, dispatch_uid='pretix_tables_nav_event')
def navbar_entry(sender, request, **kwargs):
    if not request.user.has_event_permission(request.organizer, request.event, request=request):
        return []
    url = request.resolver_match
    return [{
        'label': _('Tables'),
        'url': reverse('plugins:pretix_tables:index', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
        }),
        'active': bool(url) and url.namespace == 'plugins:pretix_tables',
        'icon': 'th-large',
    }]


@receiver(order_info, dispatch_uid='pretix_tables_order_info')
def order_info_receiver(sender, order, request, **kwargs):
    item_ids = set(order.positions.values_list('item_id', flat=True))
    if not item_ids:
        return ''

    tables = list(
        Table.objects.filter(event=sender)
        .filter(Q(table_item_id__in=item_ids) | Q(seat_item_id__in=item_ids))
        .prefetch_related('table_seats')
    )
    if not tables:
        return ''

    order_variation_ids = set(
        order.positions.filter(variation__isnull=False).values_list('variation_id', flat=True)
    )

    rows = []
    for table in tables:
        seats = []
        for seat in table.table_seats.all():
            if seat.variation_id and seat.variation_id in order_variation_ids:
                status = 'this-order'
            elif seat.has_orders():
                status = 'taken'
            else:
                status = 'free'
            seats.append({'number': seat.seat_number, 'status': status})
        rows.append({'table': table, 'seats': seats})

    return render_to_string('pretix_tables/control/order_info.html', {'tables': rows})
