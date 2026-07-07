from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver

class Produto(models.Model):
    nome = models.CharField(max_length=100, help_text="Ex: Cigarro Marca X, Fumo de Rolo Y")
    categoria = models.CharField(max_length=50, help_text="Ex: Produto Final, Matéria Prima")
    preco_custo = models.DecimalField(max_digits=10, decimal_places=2, help_text="Para matérias-primas, digite o custo. Para produtos finais, pode deixar 0 (será calculado).")
    estoque_minimo = models.FloatField(default=10, help_text="Quantidade mínima para disparar o alerta")
    preco_venda = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Preço de venda (apenas para produtos finais)")

    def __str__(self):
        return self.nome
    
    @property
    def margem_lucro_unidade(self):
        venda = float(self.preco_venda or 0)
        # Usa a nossa função inteligente que soma os insumos, e não mais o campo estático
        custo = float(self.custo_real)
        return round(venda - custo, 2)
    
    @property
    def custo_unitario_composicao(self):
        # Soma o preço de custo de cada insumo na receita
        total = 0
        composicoes = self.composicao_set.all() # Pega a "receita" do produto
        for item in composicoes:
            # Pega o último preço de compra do insumo no estoque ou produto
            preco_insumo = item.materia_prima.preco_custo or 0
            total += float(item.quantidade_necessaria) * float(preco_insumo)
        return round(total, 2)

    @property
    def custo_real(self):
        # Começa o cálculo com o custo base cadastrado (os seus 19,99)
        custo_total = Decimal(str(self.preco_custo)) if self.preco_custo else Decimal('0.00')
        
        # Busca todas as matérias-primas e SOMA ao valor base dinamicamente
        composicoes = self.composicoes.all()
        for item in composicoes:
            preco = Decimal(str(item.materia_prima.preco_custo))
            qtd = Decimal(str(item.quantidade_necessaria))
            custo_total += (preco * qtd)
            
        return custo_total
    
    @property
    def margem_percentual(self):
        venda = float(self.preco_venda or 0)
        custo = float(self.custo_real)
        if venda > 0:
            # Calcula quanto sobra do preço após pagar o custo
            return round(((venda - custo) / venda) * 100, 2)
        return 0

class Estoque(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.IntegerField(default=0)
    estoque_minimo = models.FloatField(default=10)
    
    def __str__(self):
        return f"{self.produto.nome} - {self.quantidade} un."

class ApontamentoProducao(models.Model):
    # Adicionamos a ligação com a OP (null=True para não quebrar os apontamentos antigos)
    op = models.ForeignKey('OrdemProducao', on_delete=models.CASCADE, related_name='apontamentos', null=True, blank=True)
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.IntegerField(help_text="Quantidade produzida neste apontamento")
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

class Cliente(models.Model):
    # Dados Principais
    nome = models.CharField(max_length=150, help_text="Nome da Loja ou Cliente")
    cnpj_cpf = models.CharField(max_length=20, blank=True, null=True, verbose_name="CNPJ ou CPF")
    inscricao_estadual = models.CharField(max_length=30, blank=True, null=True, verbose_name="Inscrição Estadual (IE)")
    
    # Contato
    telefone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Localização
    cep = models.CharField(max_length=10, blank=True, null=True)
    endereco = models.TextField(blank=True, null=True, verbose_name="Rua, Número, Bairro")
    cidade = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=2, blank=True, null=True, help_text="Sigla. Ex: MG, SP")
    observacoes = models.TextField(blank=True, null=True, help_text="Diário de bordo / Anotações do comercial")

    def __str__(self):
        return f"{self.nome} ({self.cnpj_cpf or 'Sem documento'})"
    
    limite_estoque_percentual = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=100.00, 
        verbose_name="Limite de Estoque (%)"
    )

class Venda(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, related_name='vendas')
    data_venda = models.DateTimeField(auto_now_add=True)
    observacao = models.TextField(blank=True, null=True, help_text="Opcional: Detalhes da entrega ou pagamento")

    def __str__(self):
        return f"Venda #{self.id} - {self.cliente.nome if self.cliente else 'Cliente Deletado'}"

    @property
    def total_venda(self):
        # Soma o subtotal de todos os itens desta venda
        total = sum(item.subtotal for item in self.itens.all())
        return total

class ItemVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, limit_choices_to={'categoria__icontains': 'final'})
    quantidade = models.IntegerField()
    preco_vendido = models.DecimalField(max_digits=10, decimal_places=2, help_text="Preço unitário no momento da venda")

    def __str__(self):
        return f"{self.quantidade}x {self.produto.nome}"

    @property
    def subtotal(self):
        return self.quantidade * self.preco_vendido
    
# O VIGIA DE ESTOQUE: Sempre que um "ItemVenda" for salvo, ele roda essa função
@receiver(post_save, sender=ItemVenda)
def baixar_estoque_venda(sender, instance, created, **kwargs):
    if created:  # Só roda se for uma venda nova (não na edição)
        produto = instance.produto
        # Busca o registro de estoque desse produto final
        estoque, _ = Estoque.objects.get_or_create(produto=produto)
        
        # Deduz a quantidade vendida do estoque atual
        estoque.quantidade -= instance.quantidade
        estoque.save()

class RegistroPerda(models.Model):
    MOTIVOS = [
        ('Defeito de Fabricação', 'Defeito de Fabricação'),
        ('Validade Vencida', 'Validade Vencida'),
        ('Avaria no Manuseio', 'Avaria no Manuseio'),
        ('Problema na Matéria-Prima', 'Problema na Matéria-Prima'),
        ('Outros', 'Outros')
    ]
    
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, help_text="Produto final ou Matéria-prima")
    quantidade = models.IntegerField(help_text="Quantidade perdida/descartada")
    motivo = models.CharField(max_length=50, choices=MOTIVOS)
    observacao = models.TextField(blank=True, null=True, help_text="Detalhes adicionais (opcional)")
    data_registro = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"Perda: {self.quantidade}x {self.produto.nome} ({self.motivo})"
    
class Fornecedor(models.Model):
    # Dados Principais
    nome = models.CharField(max_length=150, help_text="Razão Social ou Nome Fantasia")
    cnpj_cpf = models.CharField(max_length=20, blank=True, null=True, verbose_name="CNPJ ou CPF")
    inscricao_estadual = models.CharField(max_length=30, blank=True, null=True, verbose_name="Inscrição Estadual (IE)")
    
    # Contato
    telefone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True, help_text="Para envio de pedidos de compra")
    
    # Localização
    cep = models.CharField(max_length=10, blank=True, null=True)
    endereco = models.CharField(max_length=200, blank=True, null=True, verbose_name="Rua, Número, Bairro")
    cidade = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=2, blank=True, null=True, help_text="Sigla. Ex: MG, SP")
    
    # Administrativo
    observacao = models.TextField(blank=True, null=True, help_text="Dados bancários para PIX/Boleto, prazos de pagamento, etc.")

    def __str__(self):
        return f"{self.nome} ({self.cnpj_cpf or 'Sem documento'})"

class CompraInsumo(models.Model):
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True)
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, help_text="Matéria-prima comprada")
    quantidade = models.FloatField(help_text="Quantidade que entrou")
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, help_text="Preço pago por unidade/kg")
    data_compra = models.DateTimeField(auto_now_add=True)
    observacao = models.TextField(blank=True, null=True)

    def total_compra(self):
        return float(self.quantidade) * float(self.preco_unitario)

    def __str__(self):
        nome_fornecedor = self.fornecedor.nome if self.fornecedor else "Sem Fornecedor"
        return f"Compra: {self.quantidade}x {self.produto.nome} de {nome_fornecedor}"
    
class ContaPagar(models.Model):
    STATUS_CHOICES = [
        ('Pendente', 'Pendente'),
        ('Pago', 'Pago')
    ]
    
    descricao = models.CharField(max_length=200, help_text="Ex: Boleto Fazenda X, Conta de Luz")
    compra = models.ForeignKey(CompraInsumo, on_delete=models.SET_NULL, null=True, blank=True, help_text="Vincular a uma compra (opcional)")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data_vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pendente')
    observacao = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.descricao} - R$ {self.valor} ({self.status})"

class ContaReceber(models.Model):
    STATUS_CHOICES = [
        ('Pendente', 'Pendente'),
        ('Recebido', 'Recebido')
    ]
    
    descricao = models.CharField(max_length=200, help_text="Ex: Venda #15 - Cliente João")
    venda = models.ForeignKey(Venda, on_delete=models.SET_NULL, null=True, blank=True, help_text="Vincular a uma venda (opcional)")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data_vencimento = models.DateField()
    data_recebimento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pendente')
    observacao = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.descricao} - R$ {self.valor} ({self.status})"
    
class OrdemProducao(models.Model):
    STATUS_CHOICES = [
        ('Pendente', 'Pendente (Aguardando)'),
        ('Em Andamento', 'Em Andamento (Produzindo)'),
        ('Concluido', 'Concluído (No Estoque)'),
        ('Cancelado', 'Cancelado')
    ]
    
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, help_text="Produto final a ser fabricado")
    quantidade = models.IntegerField(help_text="Quantidade planejada para produção")
    quantidade_produzida = models.IntegerField(default=0, help_text="Quanto já foi fabricado desta OP")
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_prevista = models.DateField(help_text="Prazo de entrega / finalização")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pendente')
    observacao = models.TextField(blank=True, null=True, help_text="Ex: Lote especial para Cliente X")
    autor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    data_inicio = models.DateTimeField(null=True, blank=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    custo_historico = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    cliente = models.ForeignKey(
        'Cliente', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Cliente Destino (Opcional)"
    )

    @property
    def duracao_horas(self):
        if self.data_inicio and self.data_fim:
            delta = self.data_fim - self.data_inicio
            return round(delta.total_seconds() / 3600, 2)
        return 0

    def __str__(self):
        return f"OP #{self.id} - {self.quantidade}x {self.produto.nome} ({self.status})"
    
    @property
    def lucro_total(self):
        venda = float(self.produto.preco_venda or 0)
        # Se concluída, usa o custo travado. Se não, usa o custo médio atual do produto.
        custo = float(self.custo_historico) if (self.status == 'Concluido' and self.custo_historico) else float(self.produto.custo_real)
        return round((venda - custo) * self.quantidade, 2)
    
    @property
    def custo_total(self):
        # Pega o custo unitário (travado ou atual) e multiplica pela quantidade
        custo_unitario = float(self.custo_historico) if (self.status == 'Concluido' and self.custo_historico) else float(self.produto.custo_real)
        return round(custo_unitario * self.quantidade, 2)
    
    @property
    def quantidade_restante(self):
        # Calcula o que falta e garante que não mostre números negativos se o operador produzir a mais
        restante = self.quantidade - self.quantidade_produzida
        return restante if restante > 0 else 0
    
class Perfil(models.Model):
    TIPOS_ACESSO = [
        ('Logistica', 'Logística'),
        ('Qualidade', 'Qualidade'),
        ('Producao', 'Produção'),
        ('Financeiro', 'Financeiro'),
        ('Gerente', 'Gerente (Superadmin)'),
        ('Socios', 'Sócios (Apenas BI)'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPOS_ACESSO, default='Vendedor')
    
    # --- NOVOS CAMPOS ADICIONADOS ---
    telefone = models.CharField(max_length=20, blank=True, null=True)
    foto = models.ImageField(upload_to='fotos_perfil/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.tipo}"
    
class LogProducao(models.Model):
    op = models.ForeignKey(OrdemProducao, on_delete=models.CASCADE, related_name='logs')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    acao = models.CharField(max_length=50) # 'Criada', 'Editada', 'Iniciada', 'Concluída', 'Cancelada'
    detalhes = models.CharField(max_length=255)
    data_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OP #{self.op.id} - {self.acao} por {self.usuario.username if self.usuario else 'Sistema'}"
    
class SolicitacaoPedido(models.Model):
    STATUS_CHOICES = [
        ('Pendente', 'Pendente (Aguardando Análise)'),
        ('Aprovado', 'Aprovado'),
        ('Recusado', 'Recusado')
    ]
    
    nome_digitado = models.CharField(max_length=200, verbose_name="Nome digitado pelo cliente")
    # Aqui é onde você vai vincular o cliente real depois
    cliente_vinculado = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, help_text="Vincule ao cliente real após a análise")
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pendente')

    def __str__(self):
        return f"Solicitação #{self.id} - {self.nome_digitado} ({self.status})"

class ItemSolicitacao(models.Model):
    solicitacao = models.ForeignKey(SolicitacaoPedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.IntegerField()

    def __str__(self):
        return f"{self.quantidade}x {self.produto.nome}"