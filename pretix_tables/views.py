from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView

from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import CreateView, UpdateView
from pretix.helpers.compat import CompatDeleteView

from .forms import TableForm
from .models import Table


class TableList(EventPermissionRequiredMixin, ListView):
    model = Table
    context_object_name = 'tables'
    template_name = 'pretix_tables/control/table_list.html'
    permission = None  # any event team permission is enough to view the list
    paginate_by = 50

    def get_queryset(self):
        return self.request.event.pretix_tables.all()


class TableCreate(EventPermissionRequiredMixin, CreateView):
    model = Table
    form_class = TableForm
    template_name = 'pretix_tables/control/table_edit.html'
    permission = 'event.items:write'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = Table(event=self.request.event)
        return kwargs

    def get_success_url(self):
        return reverse('plugins:pretix_tables:index', kwargs={
            'organizer': self.request.organizer.slug,
            'event': self.request.event.slug,
        })

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        response = super().form_valid(form)
        self.object.sync_pretix_objects()
        self.object.log_action('pretix_tables.table.added', user=self.request.user, data={
            k: form.cleaned_data.get(k) for k in form.changed_data
        })
        messages.success(self.request, _('The table has been created.'))
        return response

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class TableUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Table
    form_class = TableForm
    template_name = 'pretix_tables/control/table_edit.html'
    permission = 'event.items:write'
    context_object_name = 'table'

    def get_queryset(self):
        return self.request.event.pretix_tables.all()

    def get_success_url(self):
        return reverse('plugins:pretix_tables:index', kwargs={
            'organizer': self.request.organizer.slug,
            'event': self.request.event.slug,
        })

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        self.object.sync_pretix_objects()
        self.object.log_action('pretix_tables.table.changed', user=self.request.user, data={
            k: form.cleaned_data.get(k) for k in form.changed_data
        })
        messages.success(self.request, _('Your changes have been saved.'))
        return response

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class TableDelete(EventPermissionRequiredMixin, CompatDeleteView):
    model = Table
    template_name = 'pretix_tables/control/table_delete.html'
    permission = 'event.items:write'
    context_object_name = 'table'

    def get_queryset(self):
        return self.request.event.pretix_tables.all()

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['sold_seat_count'] = self.get_object().sold_seat_count()
        return context

    def get_success_url(self):
        return reverse('plugins:pretix_tables:index', kwargs={
            'organizer': self.request.organizer.slug,
            'event': self.request.event.slug,
        })

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        table = self.object
        table.delete()
        if table.pk:
            # delete() caught a ProtectedError (existing orders) and deactivated instead.
            messages.info(request, _(
                'This table already has orders, so it could not be deleted. It has been deactivated '
                'instead so no more tables or seats can be booked.'
            ))
        else:
            messages.success(request, _('The table has been deleted.'))
        return redirect(self.get_success_url())
