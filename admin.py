from django.contrib import admin
from imagesize.models import ImageSize


class ImageSizeAdmin(admin.ModelAdmin):
    list_display = ('url', 'width', 'height', 'processed', 'digest')
    search_fields = ['url']
    list_filter = ['processed']

admin.site.register(ImageSize, ImageSizeAdmin)