from datetime import datetime, timezone

import pytest
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer


@pytest.fixture
@scopes_disabled()
def organizer():
    return Organizer.objects.create(name="Dummy", slug="dummy")


@pytest.fixture
@scopes_disabled()
def event(organizer):
    e = Event.objects.create(
        organizer=organizer,
        name="Dummy",
        slug="dummy",
        date_from=datetime(2030, 12, 27, 10, 0, 0, tzinfo=timezone.utc),
        plugins="pretix_tables",
        is_public=True,
    )
    e.settings.timezone = "Europe/Berlin"
    return e
