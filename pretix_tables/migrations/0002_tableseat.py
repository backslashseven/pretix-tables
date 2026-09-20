import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0306_alter_eventmetaproperty_unique_together'),
        ('pretix_tables', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='table',
            name='bundle',
        ),
        migrations.RemoveField(
            model_name='table',
            name='seats_quota',
        ),
        migrations.CreateModel(
            name='TableSeat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seat_number', models.PositiveIntegerField()),
                ('bundle', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='pretixbase.itembundle')),
                ('quota', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='pretixbase.quota')),
                ('table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='table_seats', to='pretix_tables.table')),
                ('variation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='pretixbase.itemvariation')),
            ],
            options={
                'ordering': ('seat_number',),
                'unique_together': {('table', 'seat_number')},
            },
        ),
    ]
