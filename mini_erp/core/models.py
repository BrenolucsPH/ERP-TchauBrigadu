from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class Produto(models.Model):
    nome = models.CharField(max_length=100, help_text="Ex: Cigarro Marca X, Fumo de Rolo Y")
    categoria = models.CharField(max_length=50, help_text="Ex: Produto Final, Matéria Prima")
    preco_custo = models.DecimalField(max_digits=10, decimal_places=2, help_text="Para matérias-primas, digite o custo. Para produtos finais, pode deixar 0 (será calculado).")

    estoque_minimo = models.IntegerField(default=20, help_text="O sistema vai alertar se o estoque ficar abaixo disso.")

    def __str__(self):
        return self.nome

    @property
    def custo_real(self):
        # Começa o cálculo com o custo base cadastrado (os seus 19,99)
        custo_total = Decimal(str(self.preco_custo)) if self.preco_custo else Decimal('0.00')
        
        # Busca todas as matérias-primas e SOMA ao valor base
        composicoes = self.composicoes.all()
        for item in composicoes:
            preco = Decimal(str(item.materia_prima.preco_custo))
            qtd = Decimal(str(item.quantidade_necessaria))
            custo_total += (preco * qtd)
            
        return custo_total
            
        if self.preco_custo:
            return Decimal(str(self.preco_custo))
        return Decimal('0.00')

class Estoque(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.produto.nome} - {self.quantidade} un."

class ApontamentoProducao(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.IntegerField(help_text="Quantidade produzida")
    data_registro = models.DateTimeField(auto_now_add=True) 
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    observacao = models.TextField(blank=True, null=True, help_text="Opcional: Lote, turno ou detalhes")

    def __str__(self):
        return f"{self.produto.nome} - {self.quantidade} un. ({self.data_registro.strftime('%d/%m/%Y')})"

class Composicao(models.Model):
    produto_final = models.ForeignKey(Produto, related_name='composicoes', on_delete=models.CASCADE)
    materia_prima = models.ForeignKey(Produto, related_name='usado_em', on_delete=models.CASCADE)
    quantidade_necessaria = models.DecimalField(max_digits=10, decimal_places=4, help_text="Quantidade desta matéria-prima usada para fazer 1 unidade do produto final")

    def __str__(self):
        return f"{self.quantidade_necessaria} un. de {self.materia_prima.nome} -> {self.produto_final.nome}"