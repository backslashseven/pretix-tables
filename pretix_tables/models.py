from decimal import Decimal

from django.db import models, transaction
from django.db.models import ProtectedError
from django.utils.translation import gettext_lazy as _
from django_scopes import scope
from i18nfield.fields import I18nCharField

from pretix.base.models import (
    CartPosition, Event, Item, ItemBundle, ItemCategory, Order, Quota, TaxRule,
)
from pretix.base.models.base import LoggedModel

# Internal marker used to find/reuse the one shared category that keeps table/seat items out of the
# normal front-page product list (see Table.get_or_create_category for why this specific combination
# of fields is required instead of the more obvious `is_addon` flag).
CATEGORY_INTERNAL_NAME = "pretix_tables:tables-and-seats"


class Table(LoggedModel):
    event = models.ForeignKey(
        Event, related_name='pretix_tables', on_delete=models.CASCADE,
    )
    name = I18nCharField(
        max_length=190,
        verbose_name=_("Table name"),
    )
    seat_count = models.PositiveIntegerField(
        verbose_name=_("Number of seats"),
    )
    table_price = models.DecimalField(
        max_digits=13, decimal_places=2,
        verbose_name=_("Price for the whole table"),
    )
    seat_price = models.DecimalField(
        max_digits=13, decimal_places=2,
        verbose_name=_("Price per seat"),
    )
    tax_rule = models.ForeignKey(
        TaxRule, null=True, blank=True, on_delete=models.PROTECT,
        verbose_name=_("Tax rule"),
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position"),
    )

    # Managed automatically by sync_pretix_objects(); not user-editable.
    table_item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    seat_item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    table_quota = models.ForeignKey(Quota, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    seats_quota = models.ForeignKey(Quota, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    bundle = models.ForeignKey(ItemBundle, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        ordering = ('position', 'pk')

    def __str__(self):
        return str(self.name)

    @staticmethod
    def get_or_create_category(event):
        category, created = ItemCategory.objects.get_or_create(
            event=event,
            internal_name=CATEGORY_INTERNAL_NAME,
            defaults={
                'name': str(_("Tables & seats")),
                'cross_selling_mode': 'only',
                'cross_selling_condition': 'products',
            },
        )
        # Guard against an organizer manually editing this category later and breaking the
        # hide-from-front-page / hide-from-generic-cross-selling mechanism it relies on.
        if category.cross_selling_mode != 'only' or category.cross_selling_condition != 'products':
            category.cross_selling_mode = 'only'
            category.cross_selling_condition = 'products'
            category.save(update_fields=['cross_selling_mode', 'cross_selling_condition'])
        return category

    def sync_pretix_objects(self):
        """
        Creates/updates the pretix core Item/Quota/ItemBundle objects that back this table, so that
        availability, locking and pricing are handled entirely by pretix's own cart/order/quota code
        instead of a bespoke mechanism. Must be called after any create/update of this Table.
        """
        with scope(organizer=self.event.organizer):
            category = self.get_or_create_category(self.event)

            item = self.table_item or Item(event=self.event)
            item.category = category
            item.name = str(_("{table} (whole table)")).format(table=self.name)
            item.default_price = self.table_price
            item.tax_rule = self.tax_rule
            item.admission = False
            item.active = self.active
            item.save()

            seat_item = self.seat_item or Item(event=self.event)
            seat_item.category = category
            seat_item.name = str(_("{table} (seat)")).format(table=self.name)
            seat_item.default_price = self.seat_price
            seat_item.tax_rule = self.tax_rule
            seat_item.admission = False
            seat_item.active = self.active
            seat_item.save()

            table_quota = self.table_quota or Quota(event=self.event)
            table_quota.name = str(_("{table}: whole table")).format(table=self.name)
            table_quota.size = 1
            table_quota.save()
            table_quota.items.set([item])

            seats_quota = self.seats_quota or Quota(event=self.event)
            seats_quota.name = str(_("{table}: seats")).format(table=self.name)
            seats_quota.size = self.seat_count
            seats_quota.save()
            seats_quota.items.set([seat_item])

            bundle = self.bundle or ItemBundle(base_item=item)
            bundle.base_item = item
            bundle.bundled_item = seat_item
            bundle.bundled_variation = None
            bundle.count = self.seat_count
            bundle.designated_price = Decimal('0.00')
            bundle.save()

            Table.objects.filter(pk=self.pk).update(
                table_item=item, seat_item=seat_item,
                table_quota=table_quota, seats_quota=seats_quota,
                bundle=bundle,
            )
            self.table_item, self.seat_item = item, seat_item
            self.table_quota, self.seats_quota, self.bundle = table_quota, seats_quota, bundle

    def sold_seat_count(self):
        """
        Number of seats already sold or awaiting payment for this table, whether booked
        individually or as part of a whole-table purchase (which bundles seat_count seat
        positions into the order).
        """
        if not self.seat_item_id:
            return 0
        with scope(organizer=self.event.organizer):
            return self.seat_item.orderposition_set.filter(
                order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID],
                canceled=False,
            ).count()

    def deactivate(self):
        with scope(organizer=self.event.organizer):
            with transaction.atomic():
                self.active = False
                self.save(update_fields=['active'])
                if self.table_item_id:
                    self.table_item.active = False
                    self.table_item.save(update_fields=['active'])
                if self.seat_item_id:
                    self.seat_item.active = False
                    self.seat_item.save(update_fields=['active'])
                if self.table_quota_id:
                    self.table_quota.size = 0
                    self.table_quota.save(update_fields=['size'])
                if self.seats_quota_id:
                    self.seats_quota.size = 0
                    self.seats_quota.save(update_fields=['size'])

    def delete(self, *args, **kwargs):
        """
        Hard-deletes this table and its managed Item/Quota/ItemBundle objects if nothing has
        ever been ordered against them. If real orders exist, those objects are protected by
        pretix core (Item -> OrderPosition is on_delete=PROTECT) and we deactivate instead,
        mirroring the behavior of pretix core's own product-deletion view.
        """
        with scope(organizer=self.event.organizer):
            try:
                with transaction.atomic():
                    # Cart reservations are disposable (unlike orders) and would otherwise
                    # block item deletion via the same PROTECT relation. Bundled positions
                    # reference their base position via a PROTECT fk of their own, so they
                    # have to go first.
                    cart_positions = CartPosition.objects.filter(item__in=[
                        i for i in (self.table_item_id, self.seat_item_id) if i
                    ])
                    cart_positions.filter(is_bundled=True).delete()
                    cart_positions.delete()
                    if self.bundle_id:
                        self.bundle.delete()
                    if self.seats_quota_id:
                        self.seats_quota.delete()
                    if self.table_quota_id:
                        self.table_quota.delete()
                    if self.seat_item_id:
                        self.seat_item.delete()
                    if self.table_item_id:
                        self.table_item.delete()
                    super().delete(*args, **kwargs)
            except ProtectedError:
                self.deactivate()
