import django.db.models.deletion
import i18nfield.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('pretixbase', '0306_alter_eventmetaproperty_unique_together'),
    ]

    operations = [
        migrations.CreateModel(
            name='Table',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', i18nfield.fields.I18nCharField(max_length=190, verbose_name='Table name')),
                ('seat_count', models.PositiveIntegerField(verbose_name='Number of seats')),
                ('table_price', models.DecimalField(decimal_places=2, max_digits=13, verbose_name='Price for the whole table')),
                ('seat_price', models.DecimalField(decimal_places=2, max_digits=13, verbose_name='Price per seat')),
                ('active', models.BooleanField(default=True, verbose_name='Active')),
                ('position', models.PositiveIntegerField(default=0, verbose_name='Position')),
                ('bundle', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='pretixbase.itembundle')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pretix_tables', to='pretixbase.event')),
                ('seat_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='pretixbase.item')),
                ('seats_quota', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='pretixbase.quota')),
                ('table_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='pretixbase.item')),
                ('table_quota', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='pretixbase.quota')),
                ('tax_rule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='pretixbase.taxrule', verbose_name='Tax rule')),
            ],
            options={
                'ordering': ('position', 'pk'),
            },
        ),
    ]
