from django import forms
from .models import Produto, Estoque, ApontamentoProducao, Composicao, RegistroPerda, Fornecedor, CompraInsumo, ContaPagar, ContaReceber, OrdemProducao, Cliente

class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        # Adicione o 'estoque_minimo' na lista de campos:
        fields = ['nome', 'categoria', 'preco_custo', 'estoque_minimo']
        
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Paiol Uva, Anilha...'}),
            'categoria': forms.Select(
                choices=[
                    ('', '--- Selecione uma Categoria ---'),
                    ('Produto Final', 'Produto Final (Tem Ficha Técnica)'),
                    ('Matéria Prima', 'Matéria-Prima / Insumo'),
                    ('Embalagem', 'Embalagem')
                ], 
                attrs={'class': 'form-select'}
            ),
            'preco_custo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            # Novo campo formatado:
            'estoque_minimo': forms.NumberInput(attrs={'class': 'form-control'}),
        }

# Adicione este bloco no final:
class EstoqueForm(forms.ModelForm):
    class Meta:
        model = Estoque
        fields = ['quantidade']
        widgets = {
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
    
class ApontamentoForm(forms.ModelForm):
    class Meta:
        model = ApontamentoProducao
        fields = ['produto', 'quantidade', 'observacao']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': '2'}),
        }

class ComposicaoForm(forms.ModelForm):
    class Meta:
        model = Composicao
        # O produto_final não entra aqui porque o sistema vai pegar sozinho pela tela
        fields = ['materia_prima', 'quantidade_necessaria']
        widgets = {
            'materia_prima': forms.Select(attrs={'class': 'form-select'}),
            # step 0.0001 permite que você coloque 0.0250 kg (25 gramas) por exemplo
            'quantidade_necessaria': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
        }

class RegistroPerdaForm(forms.ModelForm):
    class Meta:
        model = RegistroPerda
        fields = ['produto', 'quantidade', 'motivo', 'observacao']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'motivo': forms.Select(attrs={'class': 'form-select'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': '2', 'placeholder': 'Descreva o que aconteceu...'}),
        }

class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = '__all__'
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Fazenda São João'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(00) 00000-0000'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': '2'}),
        }

class CompraInsumoForm(forms.ModelForm):
    class Meta:
        model = CompraInsumo
        fields = ['fornecedor', 'produto', 'quantidade', 'preco_unitario', 'observacao']
        widgets = {
            'fornecedor': forms.Select(attrs={'class': 'form-select'}),
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'preco_unitario': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01', 'placeholder': 'R$ 0,00'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': '2', 'placeholder': 'Nº da Nota Fiscal, etc.'}),
        }

class ContaPagarForm(forms.ModelForm):
    class Meta:
        model = ContaPagar
        fields = ['descricao', 'compra', 'valor', 'data_vencimento', 'data_pagamento', 'status', 'observacao']
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Boleto Fornecedor'}),
            'compra': forms.Select(attrs={'class': 'form-select'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'data_vencimento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'data_pagamento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': '2'}),
        }

class ContaReceberForm(forms.ModelForm):
    class Meta:
        model = ContaReceber
        fields = ['descricao', 'venda', 'valor', 'data_vencimento', 'data_recebimento', 'status', 'observacao']
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Fatura Cliente'}),
            'venda': forms.Select(attrs={'class': 'form-select'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'data_vencimento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'data_recebimento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': '2'}),
        }

class OrdemProducaoForm(forms.ModelForm):
    class Meta:
        model = OrdemProducao
        fields = ['produto', 'quantidade', 'data_prevista', 'observacao', 'cliente']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'data_prevista': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': '2', 'placeholder': 'Detalhes da produção...'}),
        }

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = '__all__'