from django.contrib import admin

from django.contrib import admin
from .models import Produto, Estoque

admin.site.register(Produto)
admin.site.register(Estoque)