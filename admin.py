from django.contrib import admin
from urlproperties.models import URLProperties


class URLPropertiesAdmin(admin.ModelAdmin):
    list_display = ('url', 'bytes', 'width', 'height', 'processed')
    search_fields = ['url']
    list_filter = ['processed']

admin.site.register(URLProperties, URLPropertiesAdmin)