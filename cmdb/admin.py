from django.contrib import admin
from .models import DeviceConfig, Device

# Register your models here.
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('hostname', 'address', 'username', 'password', 'device_type')



@admin.register(DeviceConfig)
class DeviceConfigAdmin(admin.ModelAdmin):
    list_display = ('device', 'time')