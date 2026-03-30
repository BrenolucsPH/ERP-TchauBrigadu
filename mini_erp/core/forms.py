from django import forms
from .models import Produto, Estoque, ApontamentoProducao, Composicao

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