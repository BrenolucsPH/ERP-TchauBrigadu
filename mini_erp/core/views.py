from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from .models import Produto, Estoque, ApontamentoProducao, Composicao
from django.contrib import messages
from .forms import ProdutoForm, EstoqueForm, ApontamentoForm, ComposicaoForm
from django.http import HttpResponse, FileResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from datetime import datetime
from django.db.models import Sum
from django.conf import settings
import openpyxl
import json
import os

def is_admin(user):
    return user.is_superuser

@login_required
def painel_principal(request):
    ordenacao = request.GET.get('ordenar', 'nome')
    
    # 1. Filtros de Data (Pega da URL ou usa o mês atual por padrão)
    hoje = datetime.now()
    mes_filtro = request.GET.get('mes', str(hoje.month))
    ano_filtro = request.GET.get('ano', str(hoje.year))

    produtos_finais = Produto.objects.filter(categoria__icontains='final').order_by(ordenacao)
    insumos = Produto.objects.exclude(categoria__icontains='final').order_by(ordenacao)

    busca = request.GET.get('q', '')
    if busca:
        produtos_finais = produtos_finais.filter(nome__icontains=busca)
        insumos = insumos.filter(nome__icontains=busca)
    
    total_finais = produtos_finais.count()
    total_insumos = insumos.count()
    
    # 2. Cálculos Financeiros e de Estoque Atual (Mantidos)
    valor_estoque_finais = 0
    valor_estoque_insumos = 0
    alertas_estoque = 0
    
    for p in produtos_finais:
        estoque = p.estoque_set.first()
        qtd = estoque.quantidade if estoque else 0
        valor_estoque_finais += (p.custo_real * qtd)
        if qtd <= p.estoque_minimo: alertas_estoque += 1

    nomes_insumos_grafico = []
    quantidades_insumos_grafico = []
    for p in insumos:
        nomes_insumos_grafico.append(p.nome)
        estoque = p.estoque_set.first()
        qtd = estoque.quantidade if estoque else 0
        quantidades_insumos_grafico.append(qtd)
        preco = p.preco_custo if p.preco_custo else 0
        valor_estoque_insumos += (preco * qtd)
        if qtd <= p.estoque_minimo: alertas_estoque += 1
            
    capital_imobilizado = valor_estoque_finais + valor_estoque_insumos
    
    # 3. NOVA LÓGICA: Produção Mensal Dinâmica!
    apontamentos_mes = ApontamentoProducao.objects.filter(
        data_registro__year=ano_filtro,
        data_registro__month=mes_filtro
    )
    
    # 4. GRÁFICO DE EVOLUÇÃO DE CUSTOS (Linha)
    meses_labels = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    custos_mensais = []
    
    # Faz um loop de 1 a 12 (Janeiro a Dezembro) do ano selecionado
    for mes in range(1, 13):
        apontamentos_m = ApontamentoProducao.objects.filter(data_registro__year=ano_filtro, data_registro__month=mes)
        custo_mes = 0
        for ap in apontamentos_m:
            try:
                # Tenta chamar como método (se não tiver @property no models)
                custo_unitario = ap.produto.custo_real()
            except TypeError:
                # Se der erro, chama como propriedade direta
                custo_unitario = ap.produto.custo_real
                
            custo_mes += float(custo_unitario or 0) * ap.quantidade
            
        custos_mensais.append(custo_mes)
    
    # Soma total de peças produzidas no mês escolhido
    total_produzido_mes = apontamentos_mes.aggregate(Sum('quantidade'))['quantidade__sum'] or 0
    
    # Agrupa a produção por produto para gerar o novo Gráfico
    producao_agrupada = apontamentos_mes.values('produto__nome').annotate(total=Sum('quantidade')).order_by('-total')
    nomes_producao = [p['produto__nome'] for p in producao_agrupada]
    qtd_producao = [p['total'] for p in producao_agrupada]
        
    return render(request, 'painel.html', {
        'produtos_finais': produtos_finais,
        'insumos': insumos,
        'total_finais': total_finais,
        'total_insumos': total_insumos,
        'capital_imobilizado': capital_imobilizado,
        'alertas_estoque': alertas_estoque,
        'mes_filtro': mes_filtro,
        'ano_filtro': ano_filtro,
        'total_produzido_mes': total_produzido_mes,
        'nomes_producao_grafico': json.dumps(nomes_producao),
        'quantidades_producao_grafico': json.dumps(qtd_producao),
        'nomes_insumos_grafico': json.dumps(nomes_insumos_grafico),
        'quantidades_insumos_grafico': json.dumps(quantidades_insumos_grafico),
        'meses_labels_grafico': json.dumps(meses_labels),
        'custos_mensais_grafico': json.dumps(custos_mensais),
    })

@login_required
@user_passes_test(is_admin, login_url='/')
def cadastrar_produto(request):
    # Se o usuário clicou no botão "Salvar" (POST)
    if request.method == 'POST':
        form = ProdutoForm(request.POST)
        if form.is_valid():  # Verifica se não tem letras no lugar de números, etc.
            form.save()      # Salva no banco de dados!
            return redirect('painel') # Volta para a tela inicial
    
    # Se o usuário só está abrindo a tela vazia pela primeira vez (GET)
    else:
        form = ProdutoForm()
    
    return render(request, 'produto_form.html', {'form': form})

@login_required
@user_passes_test(is_admin, login_url='/')
def editar_produto(request, id):
    # Busca o produto pelo ID. Se não achar, dá erro 404 seguro.
    produto = get_object_or_404(Produto, id=id)
    
    if request.method == 'POST':
        # O "instance=produto" diz ao formulário para ATUALIZAR este item, e não criar um novo
        form = ProdutoForm(request.POST, instance=produto)
        if form.is_valid():
            form.save()
            return redirect('painel')
    else:
        # Preenche o formulário com os dados atuais do produto
        form = ProdutoForm(instance=produto)
    
    return render(request, 'produto_form.html', {'form': form, 'produto': produto})

@login_required
@user_passes_test(is_admin, login_url='/')
def excluir_produto(request, id):
    produto = get_object_or_404(Produto, id=id)
    
    if request.method == 'POST':
        # Se o usuário confirmou, deleta do banco
        produto.delete()
        return redirect('painel')
        
    # Se ele só clicou no botão de excluir, mostramos uma tela de confirmação primeiro
    return render(request, 'produto_confirmar_exclusao.html', {'produto': produto})

@login_required
@user_passes_test(is_admin, login_url='/')
def gerenciar_estoque(request, id_produto):
    # Pega o produto que o usuário clicou
    produto = get_object_or_404(Produto, id=id_produto)
    
    # Busca o estoque desse produto. Se não existir, cria um com quantidade 0.
    estoque, criado = Estoque.objects.get_or_create(produto=produto)
    
    if request.method == 'POST':
        form = EstoqueForm(request.POST, instance=estoque)
        if form.is_valid():
            form.save()
            return redirect('painel')
    else:
        form = EstoqueForm(instance=estoque)
        
    return render(request, 'estoque_form.html', {'form': form, 'produto': produto, 'estoque': estoque})

@login_required
def novo_apontamento(request):
    if request.method == 'POST':
        form = ApontamentoForm(request.POST)
        if form.is_valid():
            # Aqui entra a inteligência: Pausamos o salvamento para injetar o usuário logado
            apontamento = form.save(commit=False)
            apontamento.usuario = request.user 
            apontamento.save() # Agora sim, salvamos o apontamento de produção

            messages.success(request, f'Produção de {apontamento.quantidade}x {apontamento.produto.nome} registrada!')

            # 1. Busca o estoque do produto fabricado (ou cria um zerado se não existir)
            estoque, criado = Estoque.objects.get_or_create(produto=apontamento.produto)
            
            # 2. Soma a quantidade produzida ao saldo atual do estoque
            estoque.quantidade += apontamento.quantidade
            estoque.save() # Salva o novo saldo!

            return redirect('painel') # Manda de volta pra tela inicial
    else:
        form = ApontamentoForm()
        
    return render(request, 'apontamento_form.html', {'form': form})

@login_required
@user_passes_test(is_admin, login_url='/')
def historico_producao(request):
    # Pega todos os apontamentos, do mais novo para o mais velho
    apontamentos = ApontamentoProducao.objects.all().order_by('-data_registro')
    
    # Captura as datas que o usuário digitou no filtro (se houver)
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    
    # Se ele preencheu a data de início, filtra os maiores ou iguais (gte)
    if data_inicio:
        apontamentos = apontamentos.filter(data_registro__date__gte=data_inicio)
        
    # Se ele preencheu a data de fim, filtra os menores ou iguais (lte)
    if data_fim:
        apontamentos = apontamentos.filter(data_registro__date__lte=data_fim)
        
    return render(request, 'historico_producao.html', {
        'apontamentos': apontamentos,
        'data_inicio': data_inicio,
        'data_fim': data_fim
    })

@login_required
@user_passes_test(is_admin, login_url='/')
def ficha_tecnica(request, id_produto):
    # Pega o produto final (ex: Paiol Melancia)
    produto = get_object_or_404(Produto, id=id_produto)
    
    # Pega todos os ingredientes que já estão cadastrados para ele
    ingredientes = produto.composicoes.all()
    
    if request.method == 'POST':
        form = ComposicaoForm(request.POST)
        if form.is_valid():
            nova_composicao = form.save(commit=False)
            # Diz ao sistema que este ingrediente pertence ao Paiol da tela atual
            nova_composicao.produto_final = produto 
            nova_composicao.save()
            return redirect('ficha_tecnica', id_produto=produto.id)
    else:
        form = ComposicaoForm()
        
    return render(request, 'ficha_tecnica.html', {
        'produto': produto, 
        'ingredientes': ingredientes, 
        'form': form
    })

@login_required
@user_passes_test(is_admin, login_url='/')
def excluir_ingrediente(request, id_composicao):
    # Encontra o ingrediente específico na tabela de composição
    ingrediente = get_object_or_404(Composicao, id=id_composicao)
    
    # Guarda o ID do produto final (ex: Paiol Melancia) para sabermos para onde voltar
    id_produto_final = ingrediente.produto_final.id
    
    # Apaga o ingrediente
    ingrediente.delete()
    
    # Redireciona de volta para a ficha técnica daquele produto
    return redirect('ficha_tecnica', id_produto=id_produto_final)

@login_required
@user_passes_test(is_admin, login_url='/')
def relatorio_pdf(request):
    # Busca todos os produtos, em ordem alfabética
    produtos = Produto.objects.all().order_by('nome')
    
    # Diz ao Django qual arquivo HTML vai servir de "molde" para o PDF
    template_path = 'relatorio_pdf.html'
    context = {'produtos': produtos}
    
    # Prepara a resposta dizendo ao navegador: "Isto é um download de PDF"
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'filename="Relatorio_Estoque_Tchau_Brigadu.pdf"'
    
    # Pega o HTML, injeta os produtos e converte para PDF
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    # Se der erro, avisa
    if pisa_status.err:
        return HttpResponse('Tivemos um erro ao gerar o PDF: <pre>' + html + '</pre>')
    
    return response

@login_required
@user_passes_test(is_admin, login_url='/')
def exportar_historico_excel(request):
    # 1. Cria o arquivo Excel na memória
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Histórico de Produção"

    # 2. Cria a linha de Cabeçalhos (em negrito no Excel)
    colunas = ['Data e Hora', 'Produto Fabricado', 'Qtd. Produzida', 'Operador', 'Observação']
    ws.append(colunas)
    
    # Formata o cabeçalho para ficar em negrito
    for celula in ws[1]:
        celula.font = openpyxl.styles.Font(bold=True)

    # 3. Pega os dados (Lendo as datas do filtro da tela!)
    apontamentos = ApontamentoProducao.objects.all().order_by('-data_registro')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    
    if data_inicio:
        apontamentos = apontamentos.filter(data_registro__date__gte=data_inicio)
    if data_fim:
        apontamentos = apontamentos.filter(data_registro__date__lte=data_fim)

    # 4. Preenche as linhas com os dados
    for item in apontamentos:
        data_formatada = item.data_registro.strftime('%d/%m/%Y %H:%M')
        operador = item.usuario.username if item.usuario else 'Sistema'
        ws.append([
            data_formatada,
            item.produto.nome,
            item.quantidade,
            operador,
            item.observacao or '-'
        ])

    # 5. Prepara a resposta para o navegador baixar como arquivo .xlsx
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Historico_Producao_Tchau_Brigadu.xlsx"'
    wb.save(response)
    
    return response

@login_required
@user_passes_test(is_admin, login_url='/')
def excluir_apontamento(request, id):
    # Pega o apontamento específico
    apontamento = get_object_or_404(ApontamentoProducao, id=id)
    produto = apontamento.produto
    quantidade_produzida = apontamento.quantidade

    # 1. Remove do estoque do Produto Final
    estoque_final = produto.estoque_set.first()
    if estoque_final:
        estoque_final.quantidade -= quantidade_produzida
        estoque_final.save()

    # 2. Devolve os Insumos para o estoque (lendo a classe Composicao)
    # Correção 1: Usando o related_name 'composicoes'
    for item in produto.composicoes.all():
        insumo = item.materia_prima
        
        # Correção 2: Usando o nome exato do campo 'quantidade_necessaria'
        qtd_devolvida = item.quantidade_necessaria * quantidade_produzida
        
        estoque_insumo = insumo.estoque_set.first()
        if estoque_insumo:
            estoque_insumo.quantidade += qtd_devolvida
            estoque_insumo.save()

    # 3. Apaga o registro do histórico
    apontamento.delete()
    
    # 4. Dispara o Toast de sucesso
    messages.success(request, f'Apontamento desfeito! {quantidade_produzida}x {produto.nome} removidos e insumos devolvidos.')
    
    return redirect('historico_producao')

@login_required
def ficha_tecnica_pdf(request, id):
    # Busca o produto específico
    produto = get_object_or_404(Produto, id=id)
    
    # Busca a receita desse produto (usando o related_name 'composicoes')
    composicoes = produto.composicoes.all()
    
    # Prepara o HTML e os dados
    template_path = 'ficha_tecnica_pdf.html'
    context = {
        'produto': produto, 
        'composicoes': composicoes,
        'data_emissao': datetime.now()
    }
    
    # Configura a resposta como um arquivo PDF para download
    response = HttpResponse(content_type='application/pdf')
    # O nome do arquivo já vai com o nome do produto!
    response['Content-Disposition'] = f'filename="Ficha_Tecnica_{produto.nome}.pdf"'
    
    # Converte o HTML para PDF
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('Tivemos um erro ao gerar a Ficha Técnica em PDF.')
    
    return response

@login_required
@user_passes_test(is_admin, login_url='/')
def baixar_backup_banco(request):
    # 1. Pega o caminho exato do arquivo db.sqlite3 no seu computador
    caminho_banco = os.path.join(settings.BASE_DIR, 'db.sqlite3')
    
    # 2. Gera o nome do arquivo com a data e hora de agora (ex: backup_30-03-2026_14h30.sqlite3)
    data_agora = datetime.now().strftime('%d-%m-%Y_%Hh%M')
    nome_arquivo = f'backup_tchau_brigadu_{data_agora}.sqlite3'
    
    # 3. Abre o arquivo e manda para o navegador baixar
    if os.path.exists(caminho_banco):
        arquivo_banco = open(caminho_banco, 'rb')
        response = FileResponse(arquivo_banco, as_attachment=True, filename=nome_arquivo)
        
        # O Toast de sucesso não vai aparecer porque estamos baixando um arquivo, 
        # mas podemos registrar no console do servidor que o backup foi feito
        print(f"Backup realizado com sucesso por {request.user.username} em {data_agora}")
        return response
    else:
        messages.error(request, 'Erro crítico: Arquivo de banco de dados não encontrado!')
        return redirect('painel')