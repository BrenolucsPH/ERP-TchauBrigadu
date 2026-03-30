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
]