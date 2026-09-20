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
            sold = sorted(n for n in self.instance.sold_seat_numbers() if n > seat_count)
            if sold:
                raise forms.ValidationError(
                    _(
                        'Seat number(s) %(numbers)s already have orders against them, so you cannot '
                        'shrink the table below that.'
                    ) % {'numbers': ', '.join(str(n) for n in sold)}
                )
        return seat_count
