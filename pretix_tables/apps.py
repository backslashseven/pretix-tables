from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_tables"
    verbose_name = "pretix Tables"

    class PretixPluginMeta:
        name = gettext_lazy("pretix Tables")
        author = "Backslash Seven"
        description = gettext_lazy("Table management for pretix events.")
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=2024.1.0"

    def ready(self):
        from . import signals  # NOQA
