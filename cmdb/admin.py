from django.contrib import admin
from .models import *

# Register your models here.
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('hostname', 'address', 'username', 'password', 'device_type')



@admin.register(DeviceConfig)
class DeviceConfigAdmin(admin.ModelAdmin):
    list_display = ('device', 'time')


@admin.register(Interface)
class InterfaceAdmin(admin.ModelAdmin):
    list_display = ('config', 'interface', 'description', 'enabled')

@admin.register(LtmVirtualServer)
class LtmVirtualServerAdmin(admin.ModelAdmin):
    list_display = ('config', 'name', 'persist')


@admin.register(GtmWideip)
class GtmWideipAdmin(admin.ModelAdmin):
    list_display = ('config', 'name')