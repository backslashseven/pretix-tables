from django import forms
from django.utils.translation import gettext_lazy as _

from pretix.base.forms import I18nModelForm

from .models import Table


class TableForm(I18nModelForm):
    class Meta:
        model = Table
        fields = ['name', 'seat_count', 'table_price', 'seat_price', 'tax_rule', 'active', 'position']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tax_rule'].queryset = self.event.tax_rules.all()
        self.fields['tax_rule'].required = False

    def clean_seat_count(self):
        seat_count = self.cleaned_data['seat_count']
        if self.instance.pk:
            sold = self.instance.sold_seat_count()
            if seat_count < sold:
                raise forms.ValidationError(
                    _(
                        'This table already has %(sold)s seat(s) sold or awaiting payment. You cannot '
                        'reduce the number of seats below that.'
                    ) % {'sold': sold}
                )
        return seat_count
