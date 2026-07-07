from django.contrib import admin
from .models import Produto, Estoque, ApontamentoProducao, Composicao, Cliente, Venda, ItemVenda, SolicitacaoPedido, ItemSolicitacao

admin.site.register(Produto)
admin.site.register(Estoque)
admin.site.register(Cliente)

class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 1

@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'data_venda', 'total_venda')
    inlines = [ItemVendaInline]

class ItemSolicitacaoInline(admin.TabularInline):
    model = ItemSolicitacao
    extra = 0
    readonly_fields = ('produto', 'quantidade') # Para você não alterar o que o cliente pediu sem querer

class SolicitacaoPedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nome_digitado', 'cliente_vinculado', 'status', 'data_solicitacao')
    list_filter = ('status', 'data_solicitacao')
    list_editable = ('cliente_vinculado', 'status') # Permite que você vincule e aprove com 1 clique direto na lista!
    inlines = [ItemSolicitacaoInline]

admin.site.register(SolicitacaoPedido, SolicitacaoPedidoAdmin)