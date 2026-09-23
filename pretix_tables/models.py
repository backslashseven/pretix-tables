from decimal import Decimal

from django.db import models, transaction
from django.db.models import Max, ProtectedError
from django.utils.translation import gettext_lazy as _, override
from django_scopes import scope
from i18nfield.fields import I18nCharField
from i18nfield.strings import LazyI18nString

from pretix.base.models import (
    CartPosition, Event, Item, ItemBundle, ItemCategory, ItemVariation, Order, Quota, TaxRule,
)
from pretix.base.models.base import LoggedModel


def pin_tables_category(event):
    """
    Updates the tables category's position (if one has been created yet) to be strictly below
    every other category in the event. Written as a plain UPDATE, not .save(), so that callers
    - including the ItemCategory post_save signal in signals.py, which calls this whenever any
    category in the event is saved or reordered - don't retrigger that same signal.
    """
    category_id = event.settings.get('pretix_tables_category_id', as_type=int)
    if not category_id:
        return
    max_position = event.categories.exclude(pk=category_id).aggregate(Max('position'))['position__max']
    if max_position is None:
        return
    ItemCategory.objects.filter(pk=category_id).exclude(position=max_position + 1).update(
        position=max_position + 1
    )


def _get_or_create_tables_category(event):
    """
    Returns the single ItemCategory that all table/seat products are filed under, so they
    render as one group in the shop instead of scattered among the organizer's own categories.
    """
    category_id = event.settings.get('pretix_tables_category_id', as_type=int)
    if category_id:
        try:
            return event.categories.get(pk=category_id)
        except ItemCategory.DoesNotExist:
            pass

    result = {}
    for lang in event.settings.locales:
        with override(lang):
            result[lang] = str(_("Tables"))
    category = ItemCategory.objects.create(event=event, name=LazyI18nString(result))
    # The post_save signal fired by create() above can't pin this category's position yet -
    # it reads pretix_tables_category_id from settings, which isn't set until the next line.
    event.settings.pretix_tables_category_id = category.pk
    pin_tables_category(event)
    category.refresh_from_db(fields=['position'])
    return category


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
    table_quota = models.ForeignKey(Quota, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    seat_item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        ordering = ('position', 'pk')

    def __str__(self):
        return str(self.name)

    def _i18n_name(self, template, **kwargs):
        """
        Renders `template` in every locale enabled for this event, so I18nCharField values
        built from it (product/variation names) show correctly translated in the storefront
        regardless of which locale happened to be active when this Table was last saved -
        a plain str(_(template)) would freeze the name to just that one locale.
        """
        result = {}
        for lang in self.event.settings.locales:
            with override(lang):
                result[lang] = str(_(template)).format(table=self.name, **kwargs)
        return LazyI18nString(result)

    def sync_pretix_objects(self):
        """
        Creates/updates the pretix core Item/ItemVariation/Quota/ItemBundle objects that back
        this table, so that availability, locking, personalization, ticket generation and
        check-in are all handled entirely by pretix's own product/cart/order code. Must be
        called after any create/update of this Table.
        """
        with scope(organizer=self.event.organizer):
            category = _get_or_create_tables_category(self.event)

            item = self.table_item or Item(event=self.event)
            item.name = self._i18n_name("{table} (whole table)")
            item.category = category
            item.default_price = self.table_price
            item.tax_rule = self.tax_rule
            # The whole-table line is not itself an entry ticket - the admissions come from
            # the seats it bundles - so it never asks for attendee data or issues its own PDF.
            item.admission = False
            item.personalized = False
            item.generate_tickets = False
            item.active = self.active
            item.save()

            table_quota = self.table_quota or Quota(event=self.event)
            table_quota.name = str(_("{table}: whole table")).format(table=self.name)
            table_quota.size = 1
            table_quota.save()
            table_quota.items.set([item])

            seat_item = self.seat_item or Item(event=self.event)
            seat_item.name = self._i18n_name("{table} (seat)")
            seat_item.category = category
            seat_item.default_price = self.seat_price
            seat_item.tax_rule = self.tax_rule
            # Each seat is a normal admission ticket in its own right: attendee data is
            # collected for it and it always gets its own ticket/PDF, whether bought on its
            # own or bundled into a whole-table purchase (generate_tickets=True bypasses the
            # event's "generate tickets for bundled products" setting, which defaults to off).
            seat_item.admission = True
            seat_item.personalized = True
            seat_item.generate_tickets = True
            seat_item.active = self.active
            seat_item.save()

            Table.objects.filter(pk=self.pk).update(
                table_item=item, table_quota=table_quota, seat_item=seat_item,
            )
            self.table_item, self.table_quota, self.seat_item = item, table_quota, seat_item

            self._sync_seats(item, seat_item)

    def _sync_seats(self, table_item, seat_item):
        existing = {s.seat_number: s for s in self.table_seats.all()}

        for n in range(1, self.seat_count + 1):
            seat = existing.pop(n, None)

            var = seat.variation if seat else ItemVariation(item=seat_item)
            var.item = seat_item
            var.value = self._i18n_name("Seat {number}", number=n)
            var.position = n - 1
            var.active = True
            var.save()

            quota = seat.quota if seat else Quota(event=self.event)
            quota.name = str(_("{table}: seat {number}")).format(table=self.name, number=n)
            quota.size = 1
            quota.save()
            quota.variations.set([var])
            # pretix's own front-page product listing requires the *item* itself to be a
            # member of some quota (Exists(Quota.items.through...)) even when the actual
            # availability of a variation is governed by Quota.variations alone - core's own
            # QuotaForm always adds both for a variation selection, and QuotaAvailability's
            # position-matching only ever uses q_items for variation-less (variation_id IS
            # NULL) positions, so this has no effect on this quota's availability math, which
            # stays scoped to this one variation.
            quota.items.set([seat_item])

            # A bundle row must point at a saved variation, hence created/updated after it.
            # A previously-shrunk-then-regrown seat has its bundle row cleared (see
            # TableSeat.remove()) while keeping variation/quota alive for reuse, so `seat.bundle`
            # can be None even for an existing TableSeat - check `bundle_id`, not just `seat`.
            bundle = seat.bundle if (seat and seat.bundle_id) else ItemBundle(base_item=table_item)
            bundle.base_item = table_item
            bundle.bundled_item = seat_item
            bundle.bundled_variation = var
            bundle.count = 1
            bundle.designated_price = Decimal('0.00')
            bundle.save()

            if seat is None:
                TableSeat.objects.create(
                    table=self, seat_number=n, variation=var, quota=quota, bundle=bundle,
                )
            elif seat.bundle_id != bundle.pk:
                seat.bundle = bundle
                seat.save(update_fields=['bundle'])

        # Anything left in `existing` is a seat number beyond the new seat_count.
        for seat in existing.values():
            seat.remove(purge_cart_positions=True)

    def sold_seat_numbers(self):
        """Seat numbers that have any pending/paid order against them."""
        with scope(organizer=self.event.organizer):
            return set(
                self.table_seats.filter(
                    variation__orderposition__order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID],
                    variation__orderposition__canceled=False,
                ).values_list('seat_number', flat=True)
            )

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
                for seat in self.table_seats.all():
                    seat.deactivate()

    def delete(self, *args, **kwargs):
        """
        Hard-deletes this table and its managed Item/Quota/ItemBundle/ItemVariation objects if
        nothing has ever been ordered against them. If real orders exist, those objects are
        protected by pretix core (Item/ItemVariation -> OrderPosition is on_delete=PROTECT) and
        we deactivate instead, mirroring the behavior of pretix core's own product-deletion view.
        """
        with scope(organizer=self.event.organizer):
            try:
                with transaction.atomic():
                    for seat in list(self.table_seats.all()):
                        seat.remove(purge_cart_positions=True)

                    CartPosition.objects.filter(item_id=self.table_item_id).delete()

                    if self.table_quota_id:
                        self.table_quota.delete()
                    if self.seat_item_id:
                        self.seat_item.delete()
                    if self.table_item_id:
                        self.table_item.delete()
                    super().delete(*args, **kwargs)
            except ProtectedError:
                self.deactivate()


class TableSeat(models.Model):
    table = models.ForeignKey(Table, related_name='table_seats', on_delete=models.CASCADE)
    seat_number = models.PositiveIntegerField()
    variation = models.ForeignKey(ItemVariation, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    quota = models.ForeignKey(Quota, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    bundle = models.ForeignKey(ItemBundle, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        unique_together = ('table', 'seat_number')
        ordering = ('seat_number',)

    def __str__(self):
        return f"{self.table} - seat {self.seat_number}"

    def has_orders(self):
        if not self.variation_id:
            return False
        return self.variation.orderposition_set.filter(
            order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID],
            canceled=False,
        ).exists()

    def deactivate(self):
        if self.bundle_id:
            self.bundle.delete()
            self.bundle_id = None
        if self.variation_id:
            self.variation.active = False
            self.variation.save(update_fields=['active'])
        if self.quota_id:
            self.quota.size = 0
            self.quota.save(update_fields=['size'])
        self.save(update_fields=['bundle'])

    def remove(self, purge_cart_positions=False):
        """
        Removes this seat when the table's seat_count shrinks (or the table itself is
        deleted). The bundle row is always dropped first - a stale row pointing at an
        inactive/deleted variation would otherwise break every future whole-table purchase.
        The variation/quota are hard-deleted if unordered, or deactivated (kept, size 0) if
        real orders exist against them, exactly like the table/item-level deletion guard.
        """
        if purge_cart_positions and self.variation_id:
            cart_positions = CartPosition.objects.filter(variation_id=self.variation_id)
            cart_positions.filter(is_bundled=True).delete()
            cart_positions.delete()

        if self.bundle_id:
            self.bundle.delete()

        if self.has_orders():
            if self.variation_id:
                self.variation.active = False
                self.variation.save(update_fields=['active'])
            if self.quota_id:
                self.quota.size = 0
                self.quota.save(update_fields=['size'])
            self.bundle = None
            self.save(update_fields=['bundle'])
        else:
            if self.quota_id:
                self.quota.delete()
            if self.variation_id:
                self.variation.delete()
            self.delete()
