from django.urls import re_path

from .views import TableCreate, TableDelete, TableList, TableUpdate

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/tables/$',
            TableList.as_view(), name='index'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/tables/add$',
            TableCreate.as_view(), name='create'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/tables/(?P<pk>\d+)/$',
            TableUpdate.as_view(), name='edit'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/tables/(?P<pk>\d+)/delete$',
            TableDelete.as_view(), name='delete'),
]
