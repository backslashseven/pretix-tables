from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pretix.control.signals import nav_event
from pretix.presale.signals import checkout_flow_steps


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


@receiver(checkout_flow_steps, dispatch_uid='pretix_tables_checkout_flow_step')
def register_tables_step(sender, **kwargs):
    from .checkoutflow import TablesStep
    return TablesStep
