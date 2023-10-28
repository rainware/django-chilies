import django

if django.VERSION[0] >= 4:
    from django.utils.translation import gettext_lazy
    django.utils.translation.ugettext_lazy = gettext_lazy
