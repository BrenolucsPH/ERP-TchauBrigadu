from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from .models import Produto, Estoque, ApontamentoProducao, Composicao, Cliente, Venda, ItemVenda, RegistroPerda, Fornecedor, CompraInsumo, ContaPagar, ContaReceber, OrdemProducao, Perfil, LogProducao, SolicitacaoPedido, ItemSolicitacao
from django.contrib import messages
from .forms import ProdutoForm, EstoqueForm, ApontamentoForm, ComposicaoForm, RegistroPerdaForm, FornecedorForm, CompraInsumoForm, ContaPagarForm, ContaReceberForm, OrdemProducaoForm, ClienteForm
from django.http import HttpResponse, FileResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from datetime import datetime, timedelta
from django.db.models import Sum, F
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash
from django.db import models
from decimal import Decimal 
import csv
import openpyxl
import json
import os

# --- NOVAS SEGURANÇAS DE ACESSO (Cargos Setoriais) ---
def is_gerente(user):
    if user.is_superuser: return True
    if hasattr(user, 'perfil') and user.perfil.tipo == 'Gerente': return True
    return False

def has_logistica(user):
    if user.is_superuser: return True
    if hasattr(user, 'perfil') and user.perfil.tipo in ['Gerente', 'Logistica']: return True
    return False

def has_qualidade(user):
    if user.is_superuser: return True
    if hasattr(user, 'perfil') and user.perfil.tipo in ['Gerente', 'Qualidade']: return True
    return False

def has_producao(user):
    if user.is_superuser: return True
    if hasattr(user, 'perfil') and user.perfil.tipo in ['Gerente', 'Producao']: return True
    return False

def has_financeiro(user):
    if user.is_superuser: return True
    if hasattr(user, 'perfil') and user.perfil.tipo in ['Gerente', 'Financeiro']: return True
    return False

def has_socios_bi(user):
    if user.is_superuser: return True
    if hasattr(user, 'perfil') and user.perfil.tipo in ['Gerente', 'Socios']: return True
    return False

def obter_cargo(user):
    if user.is_superuser: return 'Gerente'
    if hasattr(user, 'perfil'): return user.perfil.tipo
    return 'Sem Cargo'

# ==========================================

@login_required
def painel_principal(request):
    # 1. FILTROS DE DATA (Mês e Ano)
    hoje = datetime.now()
    mes_filtro = int(request.GET.get('mes', hoje.month))
    ano_filtro = int(request.GET.get('ano', hoje.year))

    # 2. FILTROS DE DATA E ORDENAÇÃO
    hoje = datetime.now()
    mes_filtro = int(request.GET.get('mes', hoje.month))
    ano_filtro = int(request.GET.get('ano', hoje.year))
    
    # Restaura o nome original "ordenar" que você usava
    ordenacao = request.GET.get('ordenar', 'nome')
    
    # Restaura as suas 4 opções originais (A-Z, Z-A, Recentes, Antigos)
    opcoes_validas = ['nome', '-nome', '-id', 'id']
    if ordenacao not in opcoes_validas:
        ordenacao = 'nome'

    # 3. DADOS GERAIS E LISTAS DE PRODUTOS
    produtos_finais = Produto.objects.filter(categoria__icontains='final').order_by(ordenacao)
    insumos = Produto.objects.exclude(categoria__icontains='final').order_by(ordenacao)
    total_tipos_insumos = insumos.count()

    # Cálculos para os Cards (Estoque Total e Capital Imobilizado)
    estoques = Estoque.objects.all()
    
    total_finais = 0
    total_insumos = 0
    capital_imobilizado = 0
    
    for est in estoques:
        if 'final' in est.produto.categoria.lower():
            total_finais += est.quantidade
            try:
                custo = est.produto.custo_real()
            except TypeError:
                custo = est.produto.custo_real
            capital_imobilizado += float(custo or 0) * est.quantidade
            
        else:
            total_insumos += est.quantidade
            capital_imobilizado += float(est.produto.preco_custo or 0) * est.quantidade

    from django.db.models import F
    alertas_estoque = Estoque.objects.filter(quantidade__lte=F('produto__estoque_minimo')).count()

    # 4. GRÁFICOS DE PRODUÇÃO, CONSUMO E ESTOQUE
    apontamentos_mes = ApontamentoProducao.objects.filter(data_registro__year=ano_filtro, data_registro__month=mes_filtro)
    total_produzido_mes = sum(ap.quantidade for ap in apontamentos_mes)
    
    dict_producao = {}
    dict_consumo = {}
    
    # --- Gráfico 1 e 2: Produção e Consumo do Mês ---
    for ap in apontamentos_mes:
        nome_prod = ap.produto.nome
        dict_producao[nome_prod] = dict_producao.get(nome_prod, 0) + ap.quantidade
        
        composicoes = Composicao.objects.filter(produto_final=ap.produto)
        for comp in composicoes:
            nome_insumo = comp.materia_prima.nome
            qtd_usada = comp.quantidade_necessaria * ap.quantidade
            dict_consumo[nome_insumo] = dict_consumo.get(nome_insumo, 0) + qtd_usada

    nomes_producao = list(dict_producao.keys())
    qtd_producao = list(dict_producao.values())
    
    nomes_consumo_grafico = list(dict_consumo.keys())
    quantidades_consumo_grafico = [float(v) for v in dict_consumo.values()]

    # --- NOVO Gráfico: Estoque Atual na Prateleira ---
    nomes_estoque_grafico = []
    quantidades_estoque_grafico = []
    
    for insumo in insumos:
        estoque_item = Estoque.objects.filter(produto=insumo).first()
        qtd = estoque_item.quantidade if estoque_item else 0
        nomes_estoque_grafico.append(insumo.nome)
        quantidades_estoque_grafico.append(float(qtd))

    # 5. GRÁFICO DE EVOLUÇÃO FINANCEIRA (Receita vs Custos ao longo do ano)
    meses_labels = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    custos_mensais = []
    faturamento_mensal = []
    
    for mes in range(1, 13):
        # Custos do Mês
        apontamentos_m = ApontamentoProducao.objects.filter(data_registro__year=ano_filtro, data_registro__month=mes)
        custo_mes = 0
        for ap in apontamentos_m:
            try:
                custo_unitario = ap.produto.custo_real()
            except TypeError:
                custo_unitario = ap.produto.custo_real
            custo_mes += float(custo_unitario or 0) * ap.quantidade
        custos_mensais.append(custo_mes)
        
        # Faturamento (Receita) do Mês
        vendas_m = Venda.objects.filter(data_venda__year=ano_filtro, data_venda__month=mes)
        receita_mes = sum(float(v.total_venda) for v in vendas_m)
        faturamento_mensal.append(receita_mes)

    # 6. DADOS DOS CARDS FINANCEIROS (Mês Selecionado)
    vendas_mes_atual = Venda.objects.filter(data_venda__year=ano_filtro, data_venda__month=mes_filtro)
    faturamento_mes_atual = sum(float(v.total_venda) for v in vendas_mes_atual)
    
    custo_mes_atual = 0
    for ap in apontamentos_mes:
        try:
            c_unit = ap.produto.custo_real()
        except TypeError:
            c_unit = ap.produto.custo_real
        custo_mes_atual += float(c_unit or 0) * ap.quantidade

    # --- CÁLCULO DE PREJUÍZO COM PERDAS E GRÁFICO DE VILÕES ---
    perdas_mes_atual = RegistroPerda.objects.filter(data_registro__year=ano_filtro, data_registro__month=mes_filtro)
    prejuizo_mes_atual = 0
    dict_motivos = {}
    
    for perda in perdas_mes_atual:
        try:
            c_unit_perda = perda.produto.custo_real()
        except TypeError:
            c_unit_perda = perda.produto.custo_real
            
        valor_perdido = float(c_unit_perda or 0) * perda.quantidade
        prejuizo_mes_atual += valor_perdido
        
        motivo = perda.motivo
        dict_motivos[motivo] = dict_motivos.get(motivo, 0) + valor_perdido

    nomes_motivos_grafico = list(dict_motivos.keys())
    valores_motivos_grafico = list(dict_motivos.values())

    lucro_bruto_mes = faturamento_mes_atual - custo_mes_atual - prejuizo_mes_atual
    ops_ativas = OrdemProducao.objects.filter(status__in=['Pendente', 'Em Andamento']).count()
    ultimas_vendas = Venda.objects.all().order_by('-data_venda')[:4]

    return render(request, 'painel.html', {
        'produtos_finais': produtos_finais,
        'insumos': insumos,
        'total_finais': total_finais,
        'total_insumos': total_insumos,
        'capital_imobilizado': capital_imobilizado,
        'alertas_estoque': alertas_estoque,
        'mes_filtro': str(mes_filtro),
        'ano_filtro': str(ano_filtro),
        'total_produzido_mes': total_produzido_mes,
        'nomes_producao_grafico': json.dumps(nomes_producao),
        'quantidades_producao_grafico': json.dumps(qtd_producao),
        'nomes_insumos_grafico': json.dumps(nomes_consumo_grafico),
        'quantidades_insumos_grafico': json.dumps(quantidades_consumo_grafico),
        'nomes_estoque_grafico': json.dumps(nomes_estoque_grafico),
        'quantidades_estoque_grafico': json.dumps(quantidades_estoque_grafico),
        'meses_labels_grafico': json.dumps(meses_labels),
        'custos_mensais_grafico': json.dumps(custos_mensais),
        'faturamento_mensal_grafico': json.dumps(faturamento_mensal),
        'faturamento_mes_atual': faturamento_mes_atual,
        'lucro_bruto_mes': lucro_bruto_mes,
        'total_tipos_insumos': total_tipos_insumos,
        'ordenar': ordenacao,
        'prejuizo_mes_atual': prejuizo_mes_atual,
        'nomes_motivos_grafico': json.dumps(nomes_motivos_grafico),
        'valores_motivos_grafico': json.dumps(valores_motivos_grafico),
        'ops_ativas': ops_ativas,
        'ultimas_vendas': ultimas_vendas,
    })

@login_required
@user_passes_test(has_logistica, login_url='/')
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
@user_passes_test(has_logistica, login_url='/')
def editar_produto(request, id):
    produto = get_object_or_404(Produto, id=id)
    
    if request.method == 'POST':
        form = ProdutoForm(request.POST, instance=produto)
        if form.is_valid():
            form.save()
            messages.success(request, f'Produto "{produto.nome}" atualizado com sucesso!')
            
            # 2. LÊ A MEMÓRIA: Pega o link exato de onde você veio e te redireciona pra lá
            url_de_volta = request.session.get('url_voltar_produto', 'painel')
            return redirect(url_de_volta)
    else:
        # 1. GRAVA NA MEMÓRIA: Quando você abre a tela, ele anota a sua página anterior
        request.session['url_voltar_produto'] = request.META.get('HTTP_REFERER', 'painel')
        form = ProdutoForm(instance=produto)
    
    return render(request, 'produto_form.html', {'form': form, 'produto': produto})

@login_required
@user_passes_test(is_gerente, login_url='/')
def excluir_produto(request, id):
    produto = get_object_or_404(Produto, id=id)
    
    if request.method == 'POST':
        # Se o usuário confirmou, deleta do banco
        produto.delete()
        return redirect('painel')
        
    # Se ele só clicou no botão de excluir, mostramos uma tela de confirmação primeiro
    return render(request, 'produto_confirmar_exclusao.html', {'produto': produto})

@login_required
@user_passes_test(has_logistica, login_url='/')
def gerenciar_estoque(request, id_produto):
    # Pega o produto que o usuário clicou
    produto = get_object_or_404(Produto, id=id_produto)
    
    # Busca o estoque desse produto
    estoque, criado = Estoque.objects.get_or_create(produto=produto)
    
    if request.method == 'POST':
        form = EstoqueForm(request.POST, instance=estoque)
        if form.is_valid():
            form.save()
            # Mostra a mensagem de sucesso e VOLTA PARA O PAINEL
            messages.success(request, f'Estoque de "{produto.nome}" atualizado com sucesso!')
            return redirect('painel')
    else:
        form = EstoqueForm(instance=estoque)
        
    return render(request, 'estoque_form.html', {'form': form, 'produto': produto, 'estoque': estoque})

@login_required
@user_passes_test(has_producao, login_url='/')
def novo_apontamento(request):
    if request.method == 'POST':
        op_id = request.POST.get('op_id')
        quantidade_apontada = float(request.POST.get('quantidade'))
        
        op = get_object_or_404(OrdemProducao, id=op_id)
        produto = op.produto
        
        # 1. VERIFICA ESTOQUE PARA A QUANTIDADE APONTADA
        composicoes = Composicao.objects.filter(produto_final=produto)
        insumos_em_falta = []
        
        for comp in composicoes:
            qtd_necessaria = float(comp.quantidade_necessaria) * quantidade_apontada
            estoque_insumo = Estoque.objects.filter(produto=comp.materia_prima).first()
            qtd_atual = float(estoque_insumo.quantidade) if estoque_insumo else 0.0
            
            if qtd_atual < qtd_necessaria:
                insumos_em_falta.append(f"{comp.materia_prima.nome}")
                
        if insumos_em_falta:
            messages.error(request, f"Estoque insuficiente para apontar {quantidade_apontada} unidades. Faltam: " + ", ".join(insumos_em_falta))
            return redirect('novo_apontamento')
            
        # 2. ABATE INSUMOS E SOBE PRODUTO FINAL
        for comp in composicoes:
            qtd_necessaria = float(comp.quantidade_necessaria) * quantidade_apontada
            estoque_insumo = Estoque.objects.get(produto=comp.materia_prima)
            estoque_insumo.quantidade -= qtd_necessaria
            estoque_insumo.save()
            
        estoque_final, _ = Estoque.objects.get_or_create(produto=produto)
        estoque_final.quantidade += quantidade_apontada
        estoque_final.save()
        
        # 3. SALVA O APONTAMENTO E ATUALIZA A OP
        ApontamentoProducao.objects.create(
            op=op, produto=produto, quantidade=quantidade_apontada, usuario=request.user
        )
        
        op.quantidade_produzida += quantidade_apontada
        op.save()
        
        messages.success(request, f'Apontamento de {quantidade_apontada}x registrado na OP #{op.id}!')
        return redirect('novo_apontamento')
        
    # Na tela, mostra APENAS as OPs que estão rodando na fábrica
    ops_em_andamento = OrdemProducao.objects.filter(status='Em Andamento')
    return render(request, 'apontar_producao.html', {'ops': ops_em_andamento})

@login_required
@user_passes_test(has_producao, login_url='/')
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
@user_passes_test(has_qualidade, login_url='/')
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
@user_passes_test(has_qualidade, login_url='/')
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
@user_passes_test(has_socios_bi, login_url='/')
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
@user_passes_test(has_socios_bi, login_url='/')
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
@user_passes_test(is_gerente, login_url='/')
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
@user_passes_test(has_qualidade, login_url='/')
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
@user_passes_test(is_gerente, login_url='/')
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
    
@login_required
@user_passes_test(has_financeiro, login_url='/')
def novo_cliente_rapido(request):
    # 1. MÁGICA DA MEMÓRIA: Pega o link exato de onde você clicou no botão
    url_de_volta = request.META.get('HTTP_REFERER', 'painel')
    
    if request.method == 'POST':
        nome = request.POST.get('nome')
        telefone = request.POST.get('telefone')
        email = request.POST.get('email')
        endereco = request.POST.get('endereco')
        
        # Cria e salva o cliente no banco
        Cliente.objects.create(
            nome=nome, 
            telefone=telefone, 
            email=email, 
            endereco=endereco
        )
        
        messages.success(request, f'Cliente "{nome}" cadastrado com sucesso!')
        
    # 2. Em vez de forçar a ida pro 'painel', ele te devolve pra página de origem!
    return redirect(url_de_volta)

@login_required
@user_passes_test(has_financeiro, login_url='/')
def painel_comercial(request):
    vendas = Venda.objects.all().order_by('-data_venda')[:50]
    form_cliente = ClienteForm()

    # Dicionário fechado corretamente com a chave '}'
    context = {
        'vendas': vendas,
        'form_cliente': form_cliente,
    } 
        
    # Passando a variável 'context' com tudo dentro para o HTML
    return render(request, 'comercial.html', context)

@login_required
@user_passes_test(has_financeiro, login_url='/')
def registrar_venda(request):
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente')
        observacao = request.POST.get('observacao')
        
        produtos = request.POST.getlist('produto[]')
        quantidades = request.POST.getlist('quantidade[]')
        precos = request.POST.getlist('preco[]')
        
        if not produtos or not cliente_id:
            messages.error(request, 'Selecione um cliente e pelo menos um produto.')
            return redirect('registrar_venda')
            
        try:
            # 1. REGISTA A VENDA GERAL
            cliente = Cliente.objects.get(id=cliente_id)
            nova_venda = Venda.objects.create(cliente=cliente, observacao=observacao)
            
            total_da_venda = 0 
            ops_geradas = [] # Guarda os avisos para o vendedor saber o que foi para a fábrica
            
            for i in range(len(produtos)):
                produto_id = produtos[i]
                qtd_desejada = int(quantidades[i])
                preco = float(precos[i].replace(',', '.')) 
                
                produto_obj = Produto.objects.get(id=produto_id)
                
                # --- INTELIGÊNCIA MAKE-TO-ORDER ---
                # Olha para o stock real disponível antes de abater a venda
                estoque_obj = Estoque.objects.filter(produto=produto_obj).first()
                estoque_atual = estoque_obj.quantidade if estoque_obj else 0
                estoque_positivo = max(0, estoque_atual)
                
                # Se o cliente pedir mais do que o que há na prateleira, a fábrica tem de produzir a diferença
                if qtd_desejada > estoque_positivo:
                    qtd_a_produzir = qtd_desejada - estoque_positivo
                    
                    nova_op = OrdemProducao.objects.create(
                        produto=produto_obj,
                        quantidade=qtd_a_produzir,
                        data_prevista=timezone.now().date() + timedelta(days=3), # Dá 3 dias úteis para a fábrica
                        status='Pendente',
                        observacao=f"OP AUTOMÁTICA: Gerada para cobrir a falta de stock da Venda #{nova_venda.id} ({cliente.nome}).",
                        autor=request.user
                    )
                    ops_geradas.append(f"{qtd_a_produzir}x {produto_obj.nome}")
                
                # 2. SALVA O ITEM E ABATE O STOCK
                # (O seu Signal do models.py vai rodar aqui. Se faltar produto, o stock fica negativo propositadamente)
                ItemVenda.objects.create(
                    venda=nova_venda,
                    produto=produto_obj,
                    quantidade=qtd_desejada,
                    preco_vendido=preco
                )
                
                total_da_venda += (qtd_desejada * preco)
                
            # 3. GERA O FINANCEIRO (Conta a Receber)
            ContaReceber.objects.create(
                descricao=f"Venda #{nova_venda.id} - Cliente: {cliente.nome}",
                venda=nova_venda,
                valor=total_da_venda,
                data_vencimento=timezone.now().date(),
                status='Pendente'
            )
                
            # 4. DÁ O FEEDBACK CORRETO AO VENDEDOR
            if ops_geradas:
                msg = f"Venda #{nova_venda.id} registada! O stock não era suficiente. OPs geradas para a fábrica: " + " | ".join(ops_geradas)
                messages.warning(request, msg) # Alerta Laranja (Venda feita, mas requer produção)
            else:
                messages.success(request, f'Venda #{nova_venda.id} registada com sucesso! Tudo pronto a entregar.')
                
            return redirect('painel_comercial')
            
        except Exception as e:
            messages.error(request, f'Erro ao registar venda: {e}')
            return redirect('registrar_venda')

    # Se for GET (Apenas abrir o ecrã)
    clientes = Cliente.objects.all().order_by('nome')
    produtos = Produto.objects.filter(categoria__icontains='final').order_by('nome')
    return render(request, 'registrar_venda.html', {'clientes': clientes, 'produtos': produtos})

@login_required
@user_passes_test(has_qualidade, login_url='/')
def registrar_perda(request):
    if request.method == 'POST':
        form = RegistroPerdaForm(request.POST)
        if form.is_valid():
            perda = form.save(commit=False)
            produto = perda.produto
            qtd_perdida = perda.quantidade

            # 1. Trava de Segurança: Verifica o estoque
            estoque, criado = Estoque.objects.get_or_create(produto=produto)
            
            if estoque.quantidade < qtd_perdida:
                messages.error(request, f'Bloqueado: Você tentou dar baixa em {qtd_perdida} un. de {produto.nome}, mas o estoque atual é de apenas {estoque.quantidade} un.')
                return redirect('registrar_perda')

            # 2. Desconta do Estoque Real
            estoque.quantidade -= qtd_perdida
            estoque.save()

            # 3. Salva o histórico com quem registrou
            perda.usuario = request.user
            perda.save()

            messages.success(request, f'Perda de {qtd_perdida}x {produto.nome} registrada e descontada do estoque com sucesso!')
            return redirect('registrar_perda')
    else:
        form = RegistroPerdaForm()

    # Busca as últimas 50 perdas para mostrar na tabela
    historico_perdas = RegistroPerda.objects.all().order_by('-data_registro')[:50]

    return render(request, 'registrar_perda.html', {'form': form, 'historico_perdas': historico_perdas})

@login_required
@user_passes_test(has_logistica, login_url='/')
def registrar_compra(request):
    if request.method == 'POST':
        form = CompraInsumoForm(request.POST)
        if form.is_valid():
            compra = form.save()
            
            # 1. Busca estoque e preço atuais ANTES da atualização
            estoque, criado = Estoque.objects.get_or_create(produto=compra.produto)
            qtd_antiga = float(estoque.quantidade)
            custo_antigo = float(compra.produto.preco_custo or 0)
            
            # 2. Dados da nova compra
            qtd_nova = float(compra.quantidade)
            custo_novo = float(compra.preco_unitario)
            
            # 3. Cálculo do Custo Médio Ponderado
            # (Qtd Antiga * Custo Antigo + Qtd Nova * Custo Novo) / Quantidade Total
            total_unidades = qtd_antiga + qtd_nova
            if total_unidades > 0:
                custo_medio = ((qtd_antiga * custo_antigo) + (qtd_nova * custo_novo)) / total_unidades
            else:
                custo_medio = custo_novo

            # 4. Atualiza os dados no banco
            estoque.quantidade = total_unidades
            estoque.save()
            
            compra.produto.preco_custo = round(custo_medio, 4)
            compra.produto.save()

            # 5. Gera a Conta a Pagar
            ContaPagar.objects.create(
                descricao=f"Compra de {compra.quantidade}x {compra.produto.nome}",
                compra=compra,
                valor=compra.total_compra(),
                data_vencimento=timezone.now().date(),
                status='Pendente'
            )
            
            messages.success(request, f'Compra registrada! Custo médio de {compra.produto.nome} atualizado para R$ {custo_medio:.2f}')
            return redirect('registrar_compra')
    else:
        form = CompraInsumoForm()
        form.fields['produto'].queryset = Produto.objects.exclude(categoria__icontains='final')

    historico_compras = CompraInsumo.objects.all().order_by('-data_compra')[:50]
    return render(request, 'registrar_compra.html', {'form': form, 'historico_compras': historico_compras})


@login_required
@user_passes_test(has_logistica, login_url='/')
def cadastrar_fornecedor(request):
    if request.method == 'POST':
        form = FornecedorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Fornecedor cadastrado com sucesso!')
            return redirect('registrar_compra')
    else:
        form = FornecedorForm()
    
    return render(request, 'fornecedor_form.html', {'form': form})

from django.utils import timezone

@login_required
@user_passes_test(has_financeiro, login_url='/')
def lista_financeiro(request):
    # Precisamos da data de hoje para saber o que está atrasado
    hoje = timezone.now().date()

    # Contas a Pagar (Saídas)
    pagar_pendentes = ContaPagar.objects.filter(status='Pendente').order_by('data_vencimento')
    pagar_pagas = ContaPagar.objects.filter(status='Pago').order_by('-data_pagamento')[:10]
    
    # Contas a Receber (Entradas)
    receber_pendentes = ContaReceber.objects.filter(status='Pendente').order_by('data_vencimento')
    receber_recebidas = ContaReceber.objects.filter(status='Recebido').order_by('-data_recebimento')[:10]

    # --- INTELIGÊNCIA DE INADIMPLÊNCIA E ATRASOS ---
    # Marcamos virtualmente cada conta para o HTML saber se deve pintar de vermelho
    for conta in pagar_pendentes:
        conta.is_atrasada = conta.data_vencimento < hoje
        conta.is_vence_hoje = conta.data_vencimento == hoje

    for conta in receber_pendentes:
        conta.is_atrasada = conta.data_vencimento < hoje
        conta.is_vence_hoje = conta.data_vencimento == hoje

    # Totais Globais
    total_pagar = sum(c.valor for c in pagar_pendentes)
    total_receber = sum(c.valor for c in receber_pendentes)

    # Totais de Risco (Atrasados)
    inadimplencia = sum(c.valor for c in receber_pendentes if c.is_atrasada)
    fornecedores_atrasados = sum(c.valor for c in pagar_pendentes if c.is_atrasada)

    # Saldo Projetado (Se todo mundo pagar e você pagar todo mundo)
    saldo_projetado = total_receber - total_pagar

    if request.method == 'POST':
        if 'btn_pagar' in request.POST:
            form_pagar = ContaPagarForm(request.POST)
            if form_pagar.is_valid():
                form_pagar.save()
                messages.success(request, 'Conta a pagar registrada!')
                return redirect('lista_financeiro')
        
        elif 'btn_receber' in request.POST:
            form_receber = ContaReceberForm(request.POST)
            if form_receber.is_valid():
                form_receber.save()
                messages.success(request, 'Conta a receber registrada!')
                return redirect('lista_financeiro')

    context = {
        'pagar_pendentes': pagar_pendentes,
        'pagar_pagas': pagar_pagas,
        'receber_pendentes': receber_pendentes,
        'receber_recebidas': receber_recebidas,
        'total_pagar': total_pagar,
        'total_receber': total_receber,
        'inadimplencia': inadimplencia,
        'fornecedores_atrasados': fornecedores_atrasados,
        'saldo_projetado': saldo_projetado,
        'form_pagar': ContaPagarForm(),
        'form_receber': ContaReceberForm(),
        'hoje': hoje,
    }
    return render(request, 'financeiro_lista.html', context)

@login_required
@user_passes_test(has_financeiro, login_url='/')
def baixar_conta(request, tipo, id):
    if tipo == 'pagar':
        conta = get_object_or_404(ContaPagar, id=id)
        conta.status = 'Pago'
        conta.data_pagamento = timezone.now()
    else:
        conta = get_object_or_404(ContaReceber, id=id)
        conta.status = 'Recebido'
        conta.data_recebimento = timezone.now()
    
    conta.save()
    messages.success(request, f'Baixa registrada: {conta.descricao}')
    return redirect('lista_financeiro')

@login_required
@user_passes_test(has_logistica, login_url='/')
def estoque_detalhado(request):
    # 1. Pega os parâmetros do botão "Filtrar"
    pesquisa = request.GET.get('busca', '')
    categoria_filtro = request.GET.get('categoria', '')
    status_filtro = request.GET.get('status', '')

    # 2. Lê do banco de dados quais categorias realmente existem (ex: Matéria-Prima, Embalagem, etc)
    categorias_existentes = Produto.objects.values_list('categoria', flat=True).distinct()

    # 3. Puxa TODOS os produtos da base (Para não esconder produtos sem movimentação de estoque)
    produtos = Produto.objects.prefetch_related('estoque_set').all().order_by('nome')

    # 4. APLICA OS FILTROS DE TEXTO E CATEGORIA
    if pesquisa:
        produtos = produtos.filter(nome__icontains=pesquisa)
    
    if categoria_filtro:
        produtos = produtos.filter(categoria=categoria_filtro)

    # 5. Faz a matemática da página e constrói a lista
    total_imobilizado = 0
    lista_estoque = []
    alertas_count = 0

    for prod in produtos:
        # Busca o estoque deste produto. Se não existir na tabela, assume que tem 0.
        estoque_obj = prod.estoque_set.first()
        qtd_atual = float(estoque_obj.quantidade) if estoque_obj else 0.0
        
        estoque_min = float(prod.estoque_minimo or 0)
        is_baixo = qtd_atual <= estoque_min
        
        # APLICA O FILTRO DE STATUS (Crítico ou Zerado) MANUALMENTE
        if status_filtro == 'baixo' and not is_baixo:
            continue
        if status_filtro == 'zerado' and qtd_atual > 0:
            continue

        custo_unit = float(prod.preco_custo or 0)
        valor_total_item = custo_unit * qtd_atual
        total_imobilizado += valor_total_item
        
        if is_baixo:
            alertas_count += 1

        lista_estoque.append({
            'produto': prod,
            'quantidade': qtd_atual,
            'estoque_minimo': estoque_min,
            'is_baixo': is_baixo,
            'custo_unitario': custo_unit,
            'valor_total': valor_total_item
        })

    # Conta quantos itens sobraram após passar por todos os filtros
    total_itens_diferentes = len(lista_estoque)

    context = {
        'lista_estoque': lista_estoque,
        'total_imobilizado': total_imobilizado,
        'total_itens_diferentes': total_itens_diferentes,
        'alertas_count': alertas_count,
        'categorias_existentes': categorias_existentes,
    }
    return render(request, 'estoque_detalhado.html', context)

@login_required
@user_passes_test(has_socios_bi, login_url='/')
def relatorio_fechamento(request):
    # Pega o mês e ano da URL (ou usa o mês atual se não tiver)
    hoje = datetime.now()
    mes_filtro = int(request.GET.get('mes', hoje.month))
    ano_filtro = int(request.GET.get('ano', hoje.year))

    # 1. Busca Faturamento
    vendas = Venda.objects.filter(data_venda__year=ano_filtro, data_venda__month=mes_filtro)
    faturamento = sum(float(v.total_venda) for v in vendas)

    # 2. Busca Custos de Produção
    apontamentos = ApontamentoProducao.objects.filter(data_registro__year=ano_filtro, data_registro__month=mes_filtro)
    custo_producao = 0
    for ap in apontamentos:
        try:
            c_unit = ap.produto.custo_real()
        except TypeError:
            c_unit = ap.produto.custo_real
        custo_producao += float(c_unit or 0) * ap.quantidade

    # 3. Busca Prejuízo com Perdas
    perdas = RegistroPerda.objects.filter(data_registro__year=ano_filtro, data_registro__month=mes_filtro)
    prejuizo_perdas = 0
    for p in perdas:
        try:
            c_unit_perda = p.produto.custo_real()
        except TypeError:
            c_unit_perda = p.produto.custo_real
        prejuizo_perdas += float(c_unit_perda or 0) * p.quantidade

    # 4. Calcula o Lucro Real
    lucro_real = faturamento - custo_producao - prejuizo_perdas

    context = {
        'mes': mes_filtro,
        'ano': ano_filtro,
        'faturamento': faturamento,
        'custo_producao': custo_producao,
        'prejuizo_perdas': prejuizo_perdas,
        'lucro_real': lucro_real,
        'total_vendas': vendas.count(),
        'data_emissao': hoje,
    }
    return render(request, 'relatorio_fechamento.html', context)

@login_required
@user_passes_test(has_logistica, login_url='/')
def exportar_estoque_csv(request):
    # Prepara a resposta avisando o navegador que é um arquivo para baixar (download)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="posicao_estoque.csv"'

    # Cria o "escritor" do arquivo (usando ponto e vírgula para o Excel em português ler as colunas certinho)
    writer = csv.writer(response, delimiter=';')

    # Escreve o Cabeçalho da planilha
    writer.writerow(['Produto', 'Categoria', 'Estoque Minimo', 'Em Estoque', 'Custo Unitario (R$)', 'Valor Total (R$)'])

    # Busca os dados e escreve linha por linha
    itens_estoque = Estoque.objects.select_related('produto').all().order_by('produto__nome')
    
    for item in itens_estoque:
        custo_unit = float(item.produto.preco_custo or 0)
        valor_total = custo_unit * item.quantidade
        
        # Substitui ponto por vírgula para os centavos ficarem corretos no Excel brasileiro
        custo_str = str(round(custo_unit, 2)).replace('.', ',')
        total_str = str(round(valor_total, 2)).replace('.', ',')
        qtd_str = str(round(item.quantidade, 2)).replace('.', ',')
        
        writer.writerow([
            item.produto.nome,
            item.produto.categoria,
            item.produto.estoque_minimo,
            qtd_str,
            custo_str,
            total_str
        ])

    return response

@login_required
@user_passes_test(has_producao, login_url='/')
def gestao_ops(request):
    # --- 1. CAPTURA DOS FILTROS DA URL ---
    busca = request.GET.get('q', '')
    cliente_id = request.GET.get('cliente', '')
    produto_id = request.GET.get('produto', '')

    # --- 2. BUSCA BASE NO BANCO ---
    base_pendentes = OrdemProducao.objects.filter(status='Pendente').order_by('data_prevista')
    base_andamento = OrdemProducao.objects.filter(status='Em Andamento').order_by('data_prevista')
    base_concluidas = OrdemProducao.objects.filter(status='Concluido').order_by('-data_criacao')

    # --- 3. APLICAÇÃO DOS FILTROS ---
    from django.db.models import Q
    if busca:
        filtro_busca = Q(id__icontains=busca) | Q(cliente__nome__icontains=busca)
        base_pendentes = base_pendentes.filter(filtro_busca)
        base_andamento = base_andamento.filter(filtro_busca)
        base_concluidas = base_concluidas.filter(filtro_busca)
        
    if cliente_id:
        base_pendentes = base_pendentes.filter(cliente_id=cliente_id)
        base_andamento = base_andamento.filter(cliente_id=cliente_id)
        base_concluidas = base_concluidas.filter(cliente_id=cliente_id)

    if produto_id:
        base_pendentes = base_pendentes.filter(produto_id=produto_id)
        base_andamento = base_andamento.filter(produto_id=produto_id)
        base_concluidas = base_concluidas.filter(produto_id=produto_id)

    # --- 4. LISTAS PARA OS DROPDOWNS DO HTML ---
    # Puxa só os clientes e produtos que já têm alguma OP registrada
    clientes_filtros = Cliente.objects.filter(ordemproducao__isnull=False).distinct().order_by('nome')
    produtos_filtros = Produto.objects.filter(categoria__icontains='final').order_by('nome')

    hoje = timezone.now().date()

    # --- 5. PREPARAÇÃO DAS LISTAS PARA A TELA ---
    ops_pendentes = list(base_pendentes)
    
    ops_andamento = []
    for op in base_andamento:
        # Pega a receita do produto para listar no modal de perdas
        composicao = Composicao.objects.filter(produto_final=op.produto)
        op.insumos_da_receita = [comp.materia_prima for comp in composicao]
        ops_andamento.append(op)
        
    ops_concluidas = list(base_concluidas[:50])

    # 2. O SEMÁFORO BLINDADO E ALERTAS
    for op in ops_pendentes:
        # NOVO: Inteligência de Datas
        if op.data_prevista:
            op.is_atrasada = op.data_prevista < hoje
            op.is_hoje = op.data_prevista == hoje
        else:
            op.is_atrasada = False
            op.is_hoje = False

        op.margem_total = op.produto.margem_lucro_unidade * op.quantidade
        
        composicao = Composicao.objects.filter(produto_final=op.produto)
        pode_produzir = True
        faltantes_texto = []
        
        for comp in composicao:
            qtd_necessaria = float(comp.quantidade_necessaria) * float(op.quantidade)
            estoque_obj = Estoque.objects.filter(produto=comp.materia_prima).first()
            qtd_atual = float(estoque_obj.quantidade) if estoque_obj else 0.0
            
            falta = qtd_necessaria - qtd_atual
            if falta > 0.001:
                pode_produzir = False
                faltantes_texto.append(f"• {comp.materia_prima.nome} (Pede {qtd_necessaria:.2f}, Tem {qtd_atual:.2f})")
        
        # A MÁGICA: O Python monta a caixa verde ou vermelha pronta
        if pode_produzir:
            op.semaforo_html = '''
                <div class="badge bg-success-subtle text-success w-100 mb-2 py-2 text-start">
                    <i class="bi bi-check-all me-1"></i> Material em Estoque: OK
                </div>
            '''
        else:
            lista_vermelha = "<br>".join(faltantes_texto)
            op.semaforo_html = f'''
                <div class="badge bg-danger-subtle text-danger w-100 mb-1 py-2 text-start">
                    <i class="bi bi-exclamation-triangle-fill me-1"></i> ESTOQUE INSUFICIENTE
                </div>
                <div class="text-danger mb-2" style="font-size: 0.7rem; line-height: 1.2;">
                    <strong>Falta:</strong><br>{lista_vermelha}
                </div>
            '''

    # 3. Lógica de Salvar Nova OP (PERMITE CRIAR, MAS ALERTA SE FALTAR MATERIAL)
    if request.method == 'POST':
        form = OrdemProducaoForm(request.POST)
        if form.is_valid():
            op = form.save(commit=False)
            op.autor = request.user 
            op.status = 'Pendente' # Garante que toda OP nasça travada aqui
            
            # Verifica o estoque apenas para avisar o usuário
            composicao = Composicao.objects.filter(produto_final=op.produto)
            falta_material = False
            alertas = []
            
            for comp in composicao:
                qtd_necessaria = float(comp.quantidade_necessaria) * float(op.quantidade)
                estoque_insumo = Estoque.objects.filter(produto=comp.materia_prima).first()
                qtd_atual = float(estoque_insumo.quantidade) if estoque_insumo else 0.0
                
                if (qtd_necessaria - qtd_atual) > 0.001:
                    falta_material = True
                    alertas.append(f"{comp.materia_prima.nome} (Falta {qtd_necessaria - qtd_atual:.0f})")

            # Salva no banco de qualquer jeito (A pedido do Gestor)
            op.save() 
            
            if falta_material:
                msg = f"OP #{op.id} agendada como PENDENTE, mas atenção: Faltam materiais (" + " | ".join(alertas) + ")"
                messages.warning(request, msg) # Alerta Amarelo
            else:
                messages.success(request, f"OP #{op.id} agendada! Estoque de matérias-primas OK.")
            
            return redirect('gestao_ops')
    else:
        form = OrdemProducaoForm()
        # Mostra no formulário apenas produtos finais
        form.fields['produto'].queryset = Produto.objects.filter(categoria__icontains='final')

        # Calcula a carga horária total estimada das OPs pendentes
        total_horas_estimadas = 0
        for op in ops_pendentes:
            op.tempo_estimado = op.quantidade * 0.5 
            total_horas_estimadas += op.tempo_estimado

    context = {
        'ops_pendentes': ops_pendentes,
        'ops_andamento': ops_andamento,
        'ops_concluidas': ops_concluidas,
        'form': form,
        'total_horas_estimadas': total_horas_estimadas,
        'clientes_filtros': clientes_filtros,
        'produtos_filtros': produtos_filtros,
        'busca': busca,
        'cliente_filtro': cliente_id,
        'produto_filtro': produto_id,
    }
    return render(request, 'ordens_producao.html', context)

@login_required
@user_passes_test(has_producao, login_url='/')
def atualizar_op(request, op_id, acao):
    # Busca a Ordem de Produção ou retorna 404 se não existir
    op = get_object_or_404(OrdemProducao, id=op_id)
    
    if acao == 'iniciar':
        # --- TRAVA DE SEGURANÇA ANTES DE INICIAR A OP ---
        composicao = Composicao.objects.filter(produto_final=op.produto)
        falta_material = False
        alertas = []
        
        for comp in composicao:
            qtd_necessaria = float(comp.quantidade_necessaria) * float(op.quantidade)
            estoque_insumo = Estoque.objects.filter(produto=comp.materia_prima).first()
            qtd_atual = float(estoque_insumo.quantidade) if estoque_insumo else 0.0
            
            if (qtd_necessaria - qtd_atual) > 0.001:
                falta_material = True
                alertas.append(f"{comp.materia_prima.nome}")
        
        if falta_material:
            messages.error(request, f"PRODUÇÃO BLOQUEADA! Insumos insuficientes para OP #{op.id}. Faltam: {', '.join(alertas)}")
            return redirect('gestao_ops') 
        
        # Inicia a OP normalmente
        op.status = 'Em Andamento'
        op.data_inicio = timezone.now() 
        op.save()
        
        LogProducao.objects.create(
            op=op, usuario=request.user, acao="Iniciada", 
            detalhes="A OP foi enviada para o chão de fábrica e o cronômetro iniciado."
        )
        messages.info(request, f'OP #{op.id} iniciada! A fábrica está produzindo.')
        return redirect('gestao_ops')
        
    elif acao == 'concluir':
        if request.method == 'POST':
            # Captura as informações de perda vindas do Modal
            teve_perda = request.POST.get('teve_perda')
            insumo_perda_id = request.POST.get('insumo_perda_id')
            qtd_perda = float(request.POST.get('qtd_perda') or 0.0)
            motivo_perda = request.POST.get('motivo_perda', '')

            composicao = Composicao.objects.filter(produto_final=op.produto)
            
            # 1. DESCONTA APENAS A PERDA (O estoque principal já foi descontado no apontamento)
            for comp in composicao:
                if teve_perda == 'sim' and str(comp.materia_prima.id) == str(insumo_perda_id):
                    estoque_insumo, created = Estoque.objects.get_or_create(produto=comp.materia_prima)
                    estoque_insumo.quantidade -= qtd_perda
                    estoque_insumo.save()
                    LogProducao.objects.create(
                        op=op, usuario=request.user, acao="Perda Registrada",
                        detalhes=f"Perda informada na conclusão: {qtd_perda}x {comp.materia_prima.nome}."
                    )
            
            # 2. Finaliza a OP e TRAVA O CUSTO HISTÓRICO
            op.status = 'Concluido'
            op.data_fim = timezone.now()
            op.custo_historico = op.produto.custo_real 
            op.save()
            
            LogProducao.objects.create(
                op=op, usuario=request.user, acao="Concluída", 
                detalhes=f"Produção finalizada. Custo unitário travado."
            )
            messages.success(request, f'OP #{op.id} Concluída!')
            
        return redirect('gestao_ops')

    elif acao == 'cancelar':
        op.status = 'Cancelado'
        op.save()
        
        LogProducao.objects.create(
            op=op, 
            usuario=request.user, 
            acao="Cancelada", 
            detalhes="A Ordem de Produção foi cancelada pelo usuário."
        )
        messages.error(request, f'OP #{op.id} Cancelada.')
        return redirect('gestao_ops')

    # Fallback global de segurança: Se cair em qualquer outra ação não mapeada, ele redireciona sem quebrar a tela
    return redirect('gestao_ops')

@login_required
@user_passes_test(has_financeiro, login_url='/')
def mini_crm(request):
    hoje = timezone.now()
    ano_filtro = request.GET.get('ano', '')
    mes_filtro = request.GET.get('mes', '')
    status_divida = request.GET.get('divida', '')

    clientes = Cliente.objects.all().order_by('nome')
    lista_clientes = []
    
    for cliente in clientes:
        vendas = Venda.objects.filter(cliente=cliente)
        
        # 1. TERMÔMETRO DE INATIVIDADE (OPÇÃO 1)
        ultima_venda = vendas.order_by('-data_venda').first()
        dias_inativo = (hoje - ultima_venda.data_venda).days if ultima_venda else 999
        
        # 3. RAIO-X DE CONSUMO (OPÇÃO 3)
        # Busca os 3 produtos mais comprados por este cliente na história
        top_produtos = ItemVenda.objects.filter(venda__cliente=cliente)\
            .values('produto__nome')\
            .annotate(total_qtd=Sum('quantidade'))\
            .order_by('-total_qtd')[:3]

        # Filtros de Data (para o faturamento da tabela)
        vendas_filtradas = vendas
        if ano_filtro: vendas_filtradas = vendas_filtradas.filter(data_venda__year=int(ano_filtro))
        if mes_filtro: vendas_filtradas = vendas_filtradas.filter(data_venda__month=int(mes_filtro))
            
        total_pedidos = vendas_filtradas.count()
        total_comprado = sum(float(v.total_venda or 0) for v in vendas_filtradas)
        
        contas_pendentes = ContaReceber.objects.filter(venda__cliente=cliente, status='Pendente')
        valor_pendente = sum(float(c.valor) for c in contas_pendentes)
        is_inadimplente = valor_pendente > 0
        
        if status_divida == 'com_divida' and not is_inadimplente: continue
        if status_divida == 'sem_divida' and is_inadimplente: continue
        if (ano_filtro or mes_filtro) and total_pedidos == 0: continue
        
        lista_clientes.append({
            'cliente': cliente,
            'total_pedidos': total_pedidos,
            'total_comprado': total_comprado,
            'valor_pendente': valor_pendente,
            'is_inadimplente': is_inadimplente,
            'dias_inativo': dias_inativo,
            'top_produtos': top_produtos,
        })
        
    lista_clientes.sort(key=lambda x: x['total_comprado'], reverse=True)
    top_3 = lista_clientes[:3] if len(lista_clientes) >= 3 else lista_clientes

    context = {
        'lista_clientes': lista_clientes,
        'top_3': top_3,
        'ano_filtro': ano_filtro, 'mes_filtro': mes_filtro, 'status_divida': status_divida,
    }
    return render(request, 'mini_crm.html', context)

@login_required
@user_passes_test(has_financeiro, login_url='/')
def salvar_follow_up(request, cliente_id):
    if request.method == 'POST':
        cliente = get_object_or_404(Cliente, id=cliente_id)
        
        # Puxa os dados que você digitou lá no modal
        nova_observacao = request.POST.get('observacoes')
        novo_limite = request.POST.get('limite_estoque_percentual')
        
        # Atualiza o cliente
        cliente.observacoes = nova_observacao
        if novo_limite:
            # Substitui vírgula por ponto (caso você digite no teclado numérico brasileiro)
            novo_limite = str(novo_limite).replace(',', '.')
            cliente.limite_estoque_percentual = Decimal(novo_limite)
            
        cliente.save()
        
        messages.success(request, f"Dados do cliente {cliente.nome} atualizados com sucesso!")
        
    return redirect('mini_crm')

@login_required
@user_passes_test(has_socios_bi, login_url='/')
def dashboard_grafico(request):
    # --- 1. CAPTURA OS FILTROS DA TELA ---
    hoje = datetime.now()
    ano_filtro = int(request.GET.get('ano', hoje.year))
    mes_filtro = request.GET.get('mes', '') # Vazio = Ano todo
    categoria_filtro = request.GET.get('categoria', '')

    # Busca as categorias reais para popular a caixinha do filtro
    categorias_existentes = Produto.objects.values_list('categoria', flat=True).distinct()

    # --- 2. BUSCA TUDO DO ANO (Base) ---
    itens_venda = ItemVenda.objects.filter(venda__data_venda__year=ano_filtro)
    apontamentos = ApontamentoProducao.objects.filter(data_registro__year=ano_filtro)
    perdas = RegistroPerda.objects.filter(data_registro__year=ano_filtro)

    # --- 3. APLICA O FILTRO DE CATEGORIA (Se houver) ---
    if categoria_filtro:
        itens_venda = itens_venda.filter(produto__categoria=categoria_filtro)
        apontamentos = apontamentos.filter(produto__categoria=categoria_filtro)
        perdas = perdas.filter(produto__categoria=categoria_filtro)

    # --- 4. PREPARA GRÁFICO DE LINHAS (Este sempre mostra os 12 meses para ver a tendência) ---
    meses_labels = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    custos_mensais = []
    faturamento_mensal = []

    for m in range(1, 13):
        # Soma as vendas do mês item a item
        itens_mes = itens_venda.filter(venda__data_venda__month=m)
        rec_mes = sum(float(i.preco_vendido) * i.quantidade for i in itens_mes)
        faturamento_mensal.append(rec_mes)
        
        # Soma os custos de produção do mês
        apont_mes = apontamentos.filter(data_registro__month=m)
        custo_mes = 0
        for ap in apont_mes:
            c_unit = ap.produto.custo_real() if callable(ap.produto.custo_real) else ap.produto.custo_real
            custo_mes += float(c_unit or 0) * ap.quantidade
        custos_mensais.append(custo_mes)

    # --- 5. APLICA O FILTRO DE MÊS (Para os Cards e Gráficos Menores) ---
    if mes_filtro:
        itens_venda = itens_venda.filter(venda__data_venda__month=int(mes_filtro))
        apontamentos = apontamentos.filter(data_registro__month=int(mes_filtro))
        perdas = perdas.filter(data_registro__month=int(mes_filtro))

    # --- 6. CÁLCULO DOS CARDS DO TOPO (Respeitando os Filtros) ---
    total_faturamento = sum(float(i.preco_vendido) * i.quantidade for i in itens_venda)
    
    total_custos = 0
    for ap in apontamentos:
        c_unit = ap.produto.custo_real() if callable(ap.produto.custo_real) else ap.produto.custo_real
        total_custos += float(c_unit or 0) * ap.quantidade
        
    total_prejuizo = 0
    dict_perdas = {}
    for p in perdas:
        c_unit_p = p.produto.custo_real() if callable(p.produto.custo_real) else p.produto.custo_real
        valor_p = float(c_unit_p or 0) * p.quantidade
        total_prejuizo += valor_p
        dict_perdas[p.motivo] = dict_perdas.get(p.motivo, 0) + valor_p
        
    lucro_liquido = total_faturamento - total_custos - total_prejuizo
    perdas_auditadas = RegistroPerda.objects.all().select_related('produto', 'usuario').order_by('-data_registro')[:5]
    produtos_lucro = Produto.objects.filter(categoria__icontains='final')
    ranking_lucro = []
    
    for p in produtos_lucro:
        ranking_lucro.append({
            'nome': p.nome,
            'margem': p.margem_percentual,
            'valor_lucro': float(p.preco_venda or 0) - float(p.custo_real)
        })
    
    # Ordena pelos que dão mais margem %
    ranking_lucro = sorted(ranking_lucro, key=lambda x: x['margem'], reverse=True)[:5]

    # --- 7. TOP 5 PRODUTOS MAIS VENDIDOS ---
    dict_produtos = {}
    for item in itens_venda:
        dict_produtos[item.produto.nome] = dict_produtos.get(item.produto.nome, 0) + item.quantidade
    top_produtos = sorted(dict_produtos.items(), key=lambda x: x[1], reverse=True)[:5]

    # --- 8. TOP 5 CLIENTES VIPs (Agora dinâmico por categoria!) ---
    dict_clientes = {}
    for item in itens_venda:
        nome_cliente = item.venda.cliente.nome
        valor_item = float(item.preco_vendido) * item.quantidade
        dict_clientes[nome_cliente] = dict_clientes.get(nome_cliente, 0) + valor_item
    top_clientes = sorted(dict_clientes.items(), key=lambda x: x[1], reverse=True)[:5]

    planejado = OrdemProducao.objects.exclude(status='Cancelado').aggregate(total=Sum('quantidade'))['total'] or 0
    realizado = OrdemProducao.objects.filter(status='Concluido').aggregate(total=Sum('quantidade'))['total'] or 0

        # --- LÓGICA DE CARGA POR CATEGORIA ---
    # Pegamos todas as OPs pendentes e somamos a (quantidade * 0.5h) agrupando por categoria
    carga_trabalho = OrdemProducao.objects.exclude(status='Concluido').values('status').annotate(
        horas_totais=Sum(models.F('quantidade') * 0.5)
)

    # Preparamos as listas para o JavaScript
    categorias_carga = [item['status'] for item in carga_trabalho]
    horas_carga = [float(item['horas_totais']) for item in carga_trabalho]

    hoje = timezone.now()
    
    # 1. Cálculo de Faturamento
    vendas_mes = Venda.objects.filter(data_venda__month=hoje.month, data_venda__year=hoje.year)
    faturamento_mes = sum(float(v.total_venda or 0) for v in vendas_mes)
    
    # 2. Contagem de OPs (Ajuste os status se os seus forem diferentes)
    ops_ativas = OrdemProducao.objects.filter(status__in=['pendente', 'em_andamento']).count()
    
    # 3. Últimas Vendas
    ultimas_vendas = Venda.objects.all().order_by('-data_venda')[:5]

    context = {
        'ano_filtro': ano_filtro,
        'mes_filtro': mes_filtro,
        'categoria_filtro': categoria_filtro,
        'categorias_existentes': categorias_existentes,
        
        'total_faturamento': total_faturamento,
        'total_custos': total_custos,
        'total_prejuizo': total_prejuizo,
        'lucro_liquido': lucro_liquido,
        
        'meses_labels': json.dumps(meses_labels),
        'faturamento_mensal': json.dumps(faturamento_mensal),
        'custos_mensais': json.dumps(custos_mensais),
        
        'nomes_top_produtos': json.dumps([p[0] for p in top_produtos]),
        'qtd_top_produtos': json.dumps([p[1] for p in top_produtos]),
        
        'nomes_top_clientes': json.dumps([c[0] for c in top_clientes]),
        'valores_top_clientes': json.dumps([c[1] for c in top_clientes]),
        
        'nomes_perdas': json.dumps(list(dict_perdas.keys())),
        'valores_perdas': json.dumps(list(dict_perdas.values())),

        'prod_planejada': planejado,
        'prod_realizada': realizado,

        'categorias_carga': categorias_carga or [],
        'horas_carga': horas_carga or [],
        'perdas_auditadas': perdas_auditadas,
        'ranking_lucro': ranking_lucro,

        'faturamento_mes': faturamento_mes,
        'ops_ativas': ops_ativas,
        'ultimas_vendas': ultimas_vendas,
    }
    return render(request, 'dashboard_grafico.html', context)

@login_required
@user_passes_test(is_gerente, login_url='/')
def gestao_equipe(request):
    # Traz todos os usuários e já tenta puxar o Perfil junto para ficar rápido
    usuarios = User.objects.all().select_related('perfil').order_by('username')
    
    if request.method == 'POST':
        # Puxa os dados que vieram da janelinha (Modal) de novo funcionário
        username = request.POST.get('username')
        senha = request.POST.get('senha')
        tipo = request.POST.get('tipo_acesso')
        
        # Trava de Segurança: Não deixa criar dois usuários com o mesmo nome
        if User.objects.filter(username=username).exists():
            messages.error(request, f'Erro: O nome de usuário "{username}" já está em uso.')
        else:
            # 1. Cria a conta de acesso nativa do Django (já criptografando a senha)
            novo_user = User.objects.create_user(username=username, password=senha)
            
            # 2. Cola o "Crachá" (Perfil) no peito desse usuário
            Perfil.objects.create(user=novo_user, tipo=tipo)
            
            messages.success(request, f'Funcionário "{username}" cadastrado com sucesso como {tipo}!')
            
        return redirect('gestao_equipe')
        
    return render(request, 'equipe.html', {'usuarios': usuarios})

@login_required
@user_passes_test(is_gerente, login_url='/')
def excluir_usuario(request, id):
    user_obj = get_object_or_404(User, id=id)
    
    # Trava de Segurança Máxima: Ninguém pode deletar o SuperAdmin (Você)
    if user_obj.is_superuser:
        messages.error(request, 'Ação bloqueada: Você não pode excluir o Dono do Sistema!')
    elif user_obj == request.user:
        messages.error(request, 'Você não pode excluir a si mesmo enquanto estiver logado.')
    else:
        user_obj.delete()
        messages.success(request, 'Acesso do funcionário revogado com sucesso.')
        
    return redirect('gestao_equipe')

@login_required
@user_passes_test(is_gerente, login_url='/')
def resetar_senha(request, id):
    usuario_alvo = get_object_or_404(User, id=id)
    
    if request.method == 'POST':
        nova_senha = request.POST.get('nova_senha')
        
        # Trava de Segurança: Não deixa resetar a senha do SuperAdmin (Dono)
        if usuario_alvo.is_superuser and request.user != usuario_alvo:
            messages.error(request, 'Segurança: Você não pode alterar a senha do Dono do sistema.')
        else:
            # Mágica do Django: set_password criptografa a nova senha automaticamente
            usuario_alvo.set_password(nova_senha)
            usuario_alvo.save()
            messages.success(request, f'Senha do funcionário "{usuario_alvo.username}" redefinida com sucesso!')
            
    return redirect('gestao_equipe')

@login_required
def minha_conta(request):
    usuario = request.user
    # Garante que o usuário tem um perfil associado
    perfil, created = Perfil.objects.get_or_create(user=usuario)
    
    if request.method == 'POST':
        # Se ele clicou no botão de SALVAR DADOS
        if 'atualizar_dados' in request.POST:
            usuario.first_name = request.POST.get('first_name')
            usuario.last_name = request.POST.get('last_name')
            usuario.email = request.POST.get('email')
            usuario.save()
            
            perfil.telefone = request.POST.get('telefone')
            
            # Se ele enviou uma foto nova, atualiza
            if 'foto' in request.FILES:
                perfil.foto = request.FILES['foto']
            
            perfil.save()
            messages.success(request, 'Seus dados foram atualizados com sucesso!')
            return redirect('minha_conta')
            
        # Se ele clicou no botão de ALTERAR SENHA
        elif 'alterar_senha' in request.POST:
            senha_atual = request.POST.get('senha_atual')
            nova_senha = request.POST.get('nova_senha')
            confirmar_senha = request.POST.get('confirmar_senha')
            
            # Validações de segurança
            if not usuario.check_password(senha_atual):
                messages.error(request, 'Sua senha atual está incorreta.')
            elif nova_senha != confirmar_senha:
                messages.error(request, 'A confirmação de senha não bate com a nova senha.')
            elif len(nova_senha) < 6:
                messages.error(request, 'A nova senha deve ter pelo menos 6 caracteres.')
            else:
                usuario.set_password(nova_senha)
                usuario.save()
                # MÁGICA: Mantém o usuário logado mesmo após trocar a senha!
                update_session_auth_hash(request, usuario)
                messages.success(request, 'Senha alterada com proteção extra! Você continua logado.')
                
            return redirect('minha_conta')

    return render(request, 'minha_conta.html', {'perfil': perfil})

@login_required
@user_passes_test(has_producao, login_url='/')
def editar_op_rapida(request, id):
    op = get_object_or_404(OrdemProducao, id=id)
    
    # Trava: Não deixa editar se a OP já estiver rodando ou concluída
    if op.status in ['Concluido', 'Cancelado', 'Em Andamento']:
        messages.error(request, 'Não é possível editar uma OP que já foi iniciada, concluída ou cancelada.')
        return redirect('gestao_ops')
        
    if request.method == 'POST':
        nova_qtd = request.POST.get('quantidade')
        nova_data = request.POST.get('data_prevista')
        
        if nova_qtd and nova_data:
            op.quantidade = nova_qtd
            op.data_prevista = nova_data
            op.save()
            messages.success(request, f'OP #{op.id} atualizada com sucesso!')
            
    return redirect('gestao_ops')

@login_required
@user_passes_test(is_gerente, login_url='/') 
def auditoria_ops(request):
    # Pega os últimos 100 registros de quem mexeu nas OPs
    logs = LogProducao.objects.all().order_by('-data_registro')[:100]
    return render(request, 'auditoria_ops.html', {'logs': logs})

@login_required
@user_passes_test(has_logistica, login_url='/')
def sugestao_compras(request):
    # O 'models.F' compara a quantidade com o mínimo.
    # O '.exclude' garante que a categoria "Produto Final" fique de fora da lista de compras!
    itens_criticos = Estoque.objects.filter(
        quantidade__lte=models.F('estoque_minimo')
    ).exclude(produto__categoria__icontains='final')
    
    return render(request, 'sugestao_compras.html', {'itens_criticos': itens_criticos})

@login_required
@user_passes_test(has_logistica, login_url='/')
def painel_compras(request):
    ops_pendentes = OrdemProducao.objects.filter(status='Pendente')
    necessidade_total = {}

    for op in ops_pendentes:
        composicao = Composicao.objects.filter(produto_final=op.produto)
        for comp in composicao:
            item_id = comp.materia_prima.id
            nome = comp.materia_prima.nome
            # Cálculo da necessidade real (Qtd OP x Qtd na Receita)
            qtd_necessaria = float(comp.quantidade_necessaria) * op.quantidade
            
            if item_id not in necessidade_total:
                # Busca o stock atual uma única vez por item
                estoque_obj = Estoque.objects.filter(produto=comp.materia_prima).first()
                estoque_atual = float(estoque_obj.quantidade) if estoque_obj else 0.0
                
                necessidade_total[item_id] = {
                    'nome': nome,
                    'estoque_atual': estoque_atual,
                    'total_preciso': 0,
                    'ops_esperando': []
                }
            
            necessidade_total[item_id]['total_preciso'] += qtd_necessaria
            necessidade_total[item_id]['ops_esperando'].append(f"#{op.id}")

    # Filtrar apenas o que realmente falta comprar (onde o que preciso > o que tenho)
    lista_compras = []
    for item_id, dados in necessidade_total.items():
        if dados['total_preciso'] > dados['estoque_atual']:
            dados['faltante'] = dados['total_preciso'] - dados['estoque_atual']
            lista_compras.append(dados)

    return render(request, 'painel_compras.html', {'lista_compras': lista_compras})

@login_required
@user_passes_test(has_producao, login_url='/')
def imprimir_op(request, id):
    op = get_object_or_404(OrdemProducao, id=id)
    composicoes = Composicao.objects.filter(produto_final=op.produto)
    
    # Calcula a quantidade exata de cada insumo para o operador retirar no estoque
    for comp in composicoes:
        comp.total_necessario = float(comp.quantidade_necessaria) * op.quantidade
        
    return render(request, 'imprimir_op.html', {'op': op, 'composicoes': composicoes})

# ==========================================
# NOVA FUNÇÃO: ANÁLISE DE PREÇOS DE INSUMOS
# ==========================================
@login_required
@user_passes_test(has_logistica, login_url='/')
def analise_precos(request):
    # 1. Puxa só os insumos que já foram comprados alguma vez na vida
    insumos_comprados = Produto.objects.exclude(categoria__icontains='final').filter(comprainsumo__isnull=False).distinct().order_by('nome')
    
    # 2. Descobre qual produto o usuário quer analisar (se não escolher nenhum, pega o primeiro da lista)
    produto_id = request.GET.get('produto')
    if not produto_id and insumos_comprados.exists():
        produto_id = insumos_comprados.first().id
        
    produto_selecionado = None
    historico = []
    dados_grafico_datas = []
    dados_grafico_precos = []
    
    kpi_menor = 0
    kpi_maior = 0
    kpi_atual = 0
    
    if produto_id:
        produto_selecionado = get_object_or_404(Produto, id=produto_id)
        kpi_atual = produto_selecionado.preco_custo or 0
        
        # 3. Busca as compras na ordem do tempo (antigo pro novo) para desenhar o gráfico
        compras_asc = CompraInsumo.objects.filter(produto=produto_selecionado).order_by('data_compra')
        
        if compras_asc.exists():
            # Acha o maior e o menor preço que você já pagou
            kpi_menor = compras_asc.aggregate(models.Min('preco_unitario'))['preco_unitario__min']
            kpi_maior = compras_asc.aggregate(models.Max('preco_unitario'))['preco_unitario__max']
            
            # 4. Puxa o histórico invertido (novo pro antigo) para a Tabela
            historico = list(CompraInsumo.objects.filter(produto=produto_selecionado).order_by('-data_compra'))
            
            # 5. MÁGICA: Calcula se pagou mais caro ou mais barato em relação à compra anterior
            for i in range(len(historico) - 1):
                preco_atual_linha = float(historico[i].preco_unitario)
                preco_antigo_linha = float(historico[i+1].preco_unitario)
                
                if preco_antigo_linha > 0:
                    diferenca = preco_atual_linha - preco_antigo_linha
                    historico[i].variacao_rs = diferenca
                    historico[i].variacao_pct = (diferenca / preco_antigo_linha) * 100
                else:
                    historico[i].variacao_rs = 0
                    historico[i].variacao_pct = 0
                    
            # A primeira compra da vida não tem comparação
            if historico:
                historico[-1].variacao_rs = 0
                historico[-1].variacao_pct = 0
                
            # 6. Prepara os dados para o Chart.js
            for c in compras_asc:
                dados_grafico_datas.append(c.data_compra.strftime('%d/%m/%Y'))
                dados_grafico_precos.append(float(c.preco_unitario))
                
    context = {
        'insumos': insumos_comprados,
        'produto_selecionado': produto_selecionado,
        'historico': historico,
        'kpi_menor': kpi_menor,
        'kpi_maior': kpi_maior,
        'kpi_atual': kpi_atual,
        'grafico_datas': json.dumps(dados_grafico_datas),
        'grafico_precos': json.dumps(dados_grafico_precos),
    }
    return render(request, 'analise_precos.html', context)

def portal_pedido_cliente(request):
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente')
        cliente = Cliente.objects.get(id=cliente_id)
        
        pedido_retido = False
        itens_para_salvar = []
        
        # Analisa os produtos enviados no formulário
        for chave, valor in request.POST.items():
            if chave.startswith('produto_') and valor and int(valor) > 0:
                produto_id = chave.split('_')[1]
                produto = Produto.objects.get(id=produto_id)
                quantidade_pedida = int(valor)
                
                # VERIFICAÇÃO DO LIMITE DE ESTOQUE
                estoque_obj = Estoque.objects.filter(produto=produto).first()
                qtd_estoque = estoque_obj.quantidade if estoque_obj else 0
                
                # Regra: (Estoque * Limite do Cliente) / 100
                limite_permitido = (Decimal(qtd_estoque) * cliente.limite_estoque_percentual) / Decimal('100')
                
                if quantidade_pedida > limite_permitido:
                    pedido_retido = True # Estourou a cota! Vai para análise.
                
                itens_para_salvar.append({
                    'produto': produto,
                    'quantidade': quantidade_pedida,
                    'preco': produto.preco_venda or 0
                })

        # Só cria o pedido se ele selecionou algum produto
        if itens_para_salvar:
            nova_venda = Venda.objects.create(
                cliente=cliente,
                em_analise=pedido_retido,
                observacao="Pedido feito via Portal do Cliente"
            )
            
            for item in itens_para_salvar:
                ItemVenda.objects.create(
                    venda=nova_venda,
                    produto=item['produto'],
                    quantidade=item['quantidade'],
                    preco_vendido=item['preco']
                )
            
            # Mensagens de retorno para o celular do cliente
            if pedido_retido:
                messages.warning(request, "Seu pedido foi recebido! Porém, como os volumes ultrapassam sua cota pré-aprovada de estoque, ele passará por análise da nossa equipe antes da liberação.")
            else:
                messages.success(request, "Pedido aprovado e emitido com sucesso! Já está na nossa fila de separação.")
                
            return redirect('portal_pedido_cliente')

    # Se for requisição normal (GET), mostra a tela com os clientes e produtos finais
    contexto = {
        'clientes': Cliente.objects.all().order_by('nome'),
        'produtos': Produto.objects.filter(categoria__icontains='final').order_by('nome')
    }
    return render(request, 'pedido_cliente.html', contexto)

def portal_pedido_cliente(request):
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente')
        cliente = Cliente.objects.get(id=cliente_id)
        
        # Cria a solicitação já vinculando ao cliente oficial automaticamente!
        nova_solicitacao = SolicitacaoPedido.objects.create(
            nome_digitado=cliente.nome,
            cliente_vinculado=cliente,
            status='Pendente'
        )
        
        itens_adicionados = False
        pedido_retido = False
        
        # Varre o formulário procurando os produtos
        for chave, valor in request.POST.items():
            if chave.startswith('produto_') and valor and int(valor) > 0:
                produto_id = chave.split('_')[1]
                produto = Produto.objects.get(id=produto_id)
                quantidade_pedida = int(valor)
                
                estoque_obj = Estoque.objects.filter(produto=produto).first()
                qtd_estoque = estoque_obj.quantidade if estoque_obj else 0
                
                # Regra: (Estoque * Porcentagem do Cliente) / 100
                limite_permitido = (Decimal(qtd_estoque) * cliente.limite_estoque_percentual) / Decimal('100')
                
                if quantidade_pedida > limite_permitido:
                    pedido_retido = True # Acende o alerta de análise!
                # ----------------------------------------------------
                
                ItemSolicitacao.objects.create(
                    solicitacao=nova_solicitacao,
                    produto=produto,
                    quantidade=quantidade_pedida
                )
                itens_adicionados = True

        if not itens_adicionados:
            nova_solicitacao.delete()
            messages.error(request, "Seu carrinho está vazio. Adicione produtos antes de enviar.")
            return redirect('portal_pedido_cliente')

        # MENSAGENS DIFERENTES BASEADAS NA COTA
        if pedido_retido:
            messages.warning(request, f"Olá, {cliente.nome}! A quantidade solicitada excede o estoque disponível no momento. Seu pedido será submetido à análise, e retornaremos com uma atualização em até 24 horas.")
        else:
            messages.success(request, f"Olá, {cliente.nome}! Seu pedido foi registrado com sucesso. O processo de separação já foi iniciado por nossa equipe.")

        return redirect('portal_pedido_cliente')

    # Busca clientes e produtos para montar a tela
    contexto = {
        'clientes': Cliente.objects.all().order_by('nome'),
        'produtos': Produto.objects.filter(categoria__icontains='final').order_by('nome')
    }
    return render(request, 'pedido_cliente.html', contexto)

def is_admin(user):
    return user.is_superuser

@login_required(login_url='/admin/login/') # Exige estar logado
@user_passes_test(is_admin, login_url='/') # Expulsa se não for dono
def painel_solicitacoes(request):
    if request.method == 'POST':
        solicitacao_id = request.POST.get('solicitacao_id')
        acao = request.POST.get('acao') # Pode ser 'aprovar' ou 'recusar'
        
        solicitacao = get_object_or_404(SolicitacaoPedido, id=solicitacao_id)
        
        if acao == 'aprovar':
            cliente_id = request.POST.get('cliente_id')
            if not cliente_id:
                messages.error(request, "Para aprovar, você precisa selecionar a qual Cliente oficial este pedido pertence.")
                return redirect('painel_solicitacoes')
                
            cliente = get_object_or_404(Cliente, id=cliente_id)
            solicitacao.cliente_vinculado = cliente
            solicitacao.status = 'Aprovado'
            solicitacao.save()
            messages.success(request, f"Pedido de '{solicitacao.nome_digitado}' aprovado e vinculado à conta de {cliente.nome}!")
            
        elif acao == 'recusar':
            solicitacao.status = 'Recusado'
            solicitacao.save()
            messages.warning(request, f"Pedido de '{solicitacao.nome_digitado}' foi cancelado e arquivado.")
            
        return redirect('painel_solicitacoes')

    # Se for apenas para carregar a página, busca os pendentes e a lista de clientes
    solicitacoes_pendentes = SolicitacaoPedido.objects.filter(status='Pendente').order_by('data_solicitacao')
    clientes = Cliente.objects.all().order_by('nome')
    
    contexto = {
        'solicitacoes': solicitacoes_pendentes,
        'clientes': clientes
    }
    return render(request, 'painel_solicitacoes.html', contexto)