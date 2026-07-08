from .models import Estoque
from django.db import models

def alertas_estoque(request):
    if request.user.is_authenticated:
        # Conta quantos itens estão abaixo do mínimo agora
        contagem = Estoque.objects.filter(quantidade__lte=models.F('estoque_minimo')).count()
        return {'qtd_alerta_compras': contagem}
    return {'qtd_alerta_compras': 0}

def alertas_globais(request):
    """
    Este script roda silenciosamente em TODAS as páginas do sistema.
    Ele calcula os alertas e envia para o base.html automaticamente.
    """
    if request.user.is_authenticated:
        # Puxa a mesma regra da tela de Sugestão (Ignorando os produtos finais na bolinha vermelha!)
        qtd_alerta_compras = Estoque.objects.filter(
            quantidade__lte=models.F('estoque_minimo')
        ).exclude(produto__categoria__icontains='final').count()
        
        return {
            'qtd_alerta_compras': qtd_alerta_compras
        }
        
    # Se não estiver logado, não manda nada
    return {'qtd_alerta_compras': 0}