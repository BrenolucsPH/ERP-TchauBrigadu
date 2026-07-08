from django.contrib import admin
from django.urls import path, include
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('contas/', include('django.contrib.auth.urls')),
    path('', views.painel_principal, name='painel'),
    path('produto/novo/', views.cadastrar_produto, name='cadastrar_produto'),
    
    path('produto/editar/<int:id>/', views.editar_produto, name='editar_produto'),
    path('produto/excluir/<int:id>/', views.excluir_produto, name='excluir_produto'),
    path('estoque/<int:id_produto>/', views.gerenciar_estoque, name='gerenciar_estoque'),
    path('apontamento/novo/', views.novo_apontamento, name='novo_apontamento'),
    path('historico/', views.historico_producao, name='historico_producao'),
    path('produto/<int:id_produto>/ficha/', views.ficha_tecnica, name='ficha_tecnica'),
    path('ingrediente/excluir/<int:id_composicao>/', views.excluir_ingrediente, name='excluir_ingrediente'),
    path('relatorio/pdf/', views.relatorio_pdf, name='relatorio_pdf'),
    path('historico/exportar-excel/', views.exportar_historico_excel, name='exportar_excel'),
    path('apontamento/<int:id>/excluir/', views.excluir_apontamento, name='excluir_apontamento'),
    path('produto/<int:id>/ficha-pdf/', views.ficha_tecnica_pdf, name='ficha_tecnica_pdf'),
    path('sistema/backup/', views.baixar_backup_banco, name='backup_banco'),
    path('cliente/novo/', views.novo_cliente_rapido, name='novo_cliente_rapido'),
    path('comercial/', views.painel_comercial, name='painel_comercial'),
    path('comercial/nova-venda/', views.registrar_venda, name='registrar_venda'),
    path('qualidade/perdas/', views.registrar_perda, name='registrar_perda'),
    path('compras/', views.registrar_compra, name='registrar_compra'),
    path('compras/fornecedor/novo/', views.cadastrar_fornecedor, name='cadastrar_fornecedor'),
    path('financeiro/', views.lista_financeiro, name='lista_financeiro'),
    path('financeiro/baixar/<str:tipo>/<int:id>/', views.baixar_conta, name='baixar_conta'),
    path('estoque-detalhado/', views.estoque_detalhado, name='estoque_detalhado'),
    path('relatorio/fechamento/', views.relatorio_fechamento, name='relatorio_fechamento'),
    path('estoque-detalhado/exportar/', views.exportar_estoque_csv, name='exportar_estoque_csv'),
    path('producao/ordens/', views.gestao_ops, name='gestao_ops'),
    path('producao/ordens/<int:op_id>/<str:acao>/', views.atualizar_op, name='atualizar_op'),
    path('comercial/crm/', views.mini_crm, name='mini_crm'),
    path('dashboard-bi/', views.dashboard_grafico, name='dashboard_grafico'),
    path('configuracoes/equipe/', views.gestao_equipe, name='gestao_equipe'),
    path('configuracoes/equipe/excluir/<int:id>/', views.excluir_usuario, name='excluir_usuario'),
    path('configuracoes/equipe/reset-senha/<int:id>/', views.resetar_senha, name='resetar_senha'),
    path('minha-conta/', views.minha_conta, name='minha_conta'),
    path('producao/ops/editar/<int:id>/', views.editar_op_rapida, name='editar_op_rapida'),
    path('producao/auditoria/', views.auditoria_ops, name='auditoria_ops'),
    path('compras/sugestao/', views.sugestao_compras, name='sugestao_compras'),
    path('producao/compras/', views.painel_compras, name='painel_compras'),
    path('producao/imprimir-op/<int:id>/', views.imprimir_op, name='imprimir_op'),
    path('crm/salvar-follow-up/<int:cliente_id>/', views.salvar_follow_up, name='salvar_follow_up'),
    path('compras/analise-precos/', views.analise_precos, name='analise_precos'),
    path('pedido/', views.portal_pedido_cliente, name='portal_pedido_cliente'),
    path('painel-pedidos/', views.painel_solicitacoes, name='painel_solicitacoes'),
]

from django.conf import settings
from django.conf.urls.static import static
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)