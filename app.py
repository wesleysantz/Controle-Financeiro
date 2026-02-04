import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta
from datetime import date, datetime

load_dotenv()

app = Flask(__name__)

def get_db_connection():
    url = os.getenv('DATABASE_URL')
    conn = psycopg2.connect(url)
    return conn

def criar_tabelas():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tabelas Básicas
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            contato VARCHAR(50),
            data_cadastro DATE DEFAULT CURRENT_DATE
        );
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS emprestimos (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
            valor_total DECIMAL(10, 2) NOT NULL,
            valor_parcela DECIMAL(10, 2) NOT NULL,
            parcelas_totais INTEGER NOT NULL,
            parcelas_pagas INTEGER DEFAULT 0,
            data_inicio DATE NOT NULL,
            proximo_vencimento DATE NOT NULL,
            status VARCHAR(20) DEFAULT 'Ativo',
            valor_tomado DECIMAL(10, 2) DEFAULT 0 
        );
    ''')
    
    try:
        cur.execute("ALTER TABLE emprestimos ADD COLUMN valor_tomado DECIMAL(10, 2) DEFAULT 0;")
        conn.commit()
    except:
        conn.rollback()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS caixa (
            id SERIAL PRIMARY KEY,
            saldo DECIMAL(10, 2) DEFAULT 0
        );
    ''')
    cur.execute("INSERT INTO caixa (id, saldo) VALUES (1, 0) ON CONFLICT (id) DO NOTHING;")

    cur.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            id SERIAL PRIMARY KEY,
            cliente_nome VARCHAR(100),
            valor_pago DECIMAL(10, 2),
            data_pagamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            detalhe VARCHAR(200)
        );
    ''')

    conn.commit()
    cur.close()
    conn.close()

# --- ROTAS ---

@app.route('/')
def index():
    criar_tabelas()
    conn = get_db_connection()
    cur = conn.cursor()
    
    # AGORA BUSCAMOS TAMBÉM O 'valor_tomado' (e.valor_tomado) NA CONSULTA
    cur.execute('''
        SELECT c.nome, e.valor_total, e.parcelas_totais, e.valor_parcela, e.proximo_vencimento, e.id, e.parcelas_pagas, e.valor_tomado
        FROM emprestimos e
        JOIN clientes c ON e.cliente_id = c.id
        WHERE e.status = 'Ativo'
        ORDER BY e.proximo_vencimento ASC;
    ''')
    dados = cur.fetchall()

    cur.execute("SELECT saldo FROM caixa WHERE id = 1")
    resultado_saldo = cur.fetchone()
    saldo_disponivel = float(resultado_saldo[0]) if resultado_saldo else 0.0
    
    cur.close()
    conn.close()
    
    lista_emprestimos = []
    total_na_rua_liquido_usuario = 0.0 # Variável para somar só a SUA parte
    hoje = date.today()

    for linha in dados:
        parcelas_totais = linha[2]
        parcelas_pagas = linha[6]
        valor_parcela_bruta = float(linha[3])
        vencimento = linha[4]
        
        # Dados Financeiros para cálculo do Patrimônio Líquido
        valor_total_divida = float(linha[1])
        valor_original_tomado = float(linha[7]) if linha[7] else valor_total_divida
        
        # 1. Lucro Total do Empréstimo (Ex: 1500 - 1000 = 500)
        lucro_total = valor_total_divida - valor_original_tomado
        
        # 2. Parte do Sócio Total (Ex: 250)
        parte_socio_total = lucro_total / 2
        
        # 3. Quanto desse empréstimo é REALMENTE SEU? (Ex: 1500 - 250 = 1250)
        total_receber_usuario = valor_total_divida - parte_socio_total
        
        # 4. Quanto vale cada parcela para VOCÊ (Ex: 1250 / 1 = 1250 por parcela)
        valor_parcela_liquida_usuario = total_receber_usuario / parcelas_totais

        # 5. Soma ao patrimônio apenas as parcelas que faltam, usando o valor LÍQUIDO
        parcelas_restantes = parcelas_totais - parcelas_pagas
        total_na_rua_liquido_usuario += (parcelas_restantes * valor_parcela_liquida_usuario)

        cor_texto = "text-danger fw-bold" if vencimento < hoje else ("text-success fw-bold" if vencimento == hoje else "")

        lista_emprestimos.append({
            "cliente": linha[0],
            "valor": linha[1], # Na tabela mostra o valor cheio (o cliente deve tudo)
            "parcelas": f"{parcelas_pagas}/{parcelas_totais}",
            "valor_parcela": linha[3],
            "vencimento": vencimento.strftime('%d/%m/%Y'),
            "id": linha[5],
            "cor": cor_texto
        })

    # Patrimônio = Dinheiro na Mão + Dinheiro na Rua (Já descontado o sócio)
    caixa_total = saldo_disponivel + total_na_rua_liquido_usuario

    return render_template('index.html', emprestimos=lista_emprestimos, saldo=saldo_disponivel, caixa_total=caixa_total)

# --- CLIENTES ---
@app.route('/clientes')
def listar_clientes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT c.id, c.nome, c.contato, 
               (SELECT COUNT(*) FROM emprestimos e WHERE e.cliente_id = c.id AND e.status = 'Ativo') as tem_divida
        FROM clientes c
        ORDER BY c.nome;
    ''')
    clientes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('clientes.html', clientes=clientes)

@app.route('/novo_cliente')
def novo_cliente():
    return render_template('novo_cliente.html')

@app.route('/criar_cliente', methods=['POST'])
def criar_cliente():
    nome = request.form['nome']
    contato = request.form['contato']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO clientes (nome, contato) VALUES (%s, %s)', (nome, contato))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('listar_clientes'))

@app.route('/editar_cliente', methods=['POST'])
def editar_cliente():
    id_cliente = request.form['id']
    novo_nome = request.form['nome']
    novo_contato = request.form['contato']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE clientes SET nome = %s, contato = %s WHERE id = %s", (novo_nome, novo_contato, id_cliente))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('listar_clientes'))

@app.route('/excluir_cliente/<int:id>')
def excluir_cliente(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome FROM clientes WHERE id = %s", (id,))
    resultado = cur.fetchone()
    if resultado:
        nome_cliente = resultado[0]
        cur.execute("DELETE FROM emprestimos WHERE cliente_id = %s", (id,))
        cur.execute("DELETE FROM clientes WHERE id = %s", (id,))
        cur.execute("INSERT INTO historico (cliente_nome, valor_pago, detalhe) VALUES (%s, %s, %s)", (nome_cliente, 0, "Cliente Excluído"))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('listar_clientes'))

# --- EMPRÉSTIMOS ---
@app.route('/novo_emprestimo')
def novo_emprestimo():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM clientes ORDER BY nome")
    clientes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('novo_emprestimo.html', clientes=clientes)

@app.route('/criar_emprestimo', methods=['POST'])
def criar_emprestimo():
    cliente_id = request.form['cliente_id']
    valor_parcela = float(request.form['valor_parcela'])
    parcelas_totais = int(request.form['parcelas_totais'])
    data_inicio = request.form['data_inicio']
    proximo_vencimento = request.form['proximo_vencimento']
    
    tirado_do_caixa = float(request.form['tirado_caixa'])
    
    valor_total = valor_parcela * parcelas_totais
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT nome FROM clientes WHERE id = %s", (cliente_id,))
    nome_cliente = cur.fetchone()[0]

    cur.execute('''
        INSERT INTO emprestimos (cliente_id, valor_total, valor_parcela, parcelas_totais, data_inicio, proximo_vencimento, valor_tomado) 
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (cliente_id, valor_total, valor_parcela, parcelas_totais, data_inicio, proximo_vencimento, tirado_do_caixa))
    
    cur.execute("UPDATE caixa SET saldo = saldo - %s WHERE id = 1", (tirado_do_caixa,))
    
    cur.execute("INSERT INTO historico (cliente_nome, valor_pago, detalhe) VALUES (%s, %s, %s)", (nome_cliente, -tirado_do_caixa, "Empréstimo Concedido"))

    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/pagar_parcela/<int:id>', methods=['POST'])
def pagar_parcela(id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT e.parcelas_pagas, e.parcelas_totais, e.proximo_vencimento, 
               e.valor_parcela, e.valor_total, e.valor_tomado, c.nome 
        FROM emprestimos e
        JOIN clientes c ON e.cliente_id = c.id
        WHERE e.id = %s
    """, (id,))
    emprestimo = cur.fetchone()

    if emprestimo:
        pagas_atual = emprestimo[0]
        totais = emprestimo[1]
        vencimento_atual = emprestimo[2]
        valor_da_parcela = float(emprestimo[3])
        
        # CÁLCULO DO SÓCIO
        valor_total_divida = float(emprestimo[4])
        valor_original_emprestado = float(emprestimo[5]) if emprestimo[5] else valor_total_divida
        
        lucro_total_emprestimo = valor_total_divida - valor_original_emprestado
        lucro_desta_parcela = lucro_total_emprestimo / totais
        parte_do_socio = lucro_desta_parcela / 2
        
        valor_liquido_para_caixa = valor_da_parcela - parte_do_socio

        novas_pagas = pagas_atual + 1
        if novas_pagas >= totais:
            status = 'Quitado'
            novo_vencimento = vencimento_atual
        else:
            status = 'Ativo'
            novo_vencimento = vencimento_atual + relativedelta(months=1)

        cur.execute("UPDATE emprestimos SET parcelas_pagas = %s, proximo_vencimento = %s, status = %s WHERE id = %s", (novas_pagas, novo_vencimento, status, id))
        cur.execute("UPDATE caixa SET saldo = saldo + %s WHERE id = 1", (valor_liquido_para_caixa,))
        
        nome_cliente = emprestimo[6]
        detalhe_hist = f"Parcela {novas_pagas}/{totais} (Sócio recebeu R$ {parte_do_socio:.2f})"
        
        cur.execute("INSERT INTO historico (cliente_nome, valor_pago, detalhe) VALUES (%s, %s, %s)", (nome_cliente, valor_liquido_para_caixa, detalhe_hist))
        
        conn.commit()

    cur.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/adicionar_caixa', methods=['POST'])
def adicionar_caixa():
    valor_add = float(request.form['valor_adicionar'])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE caixa SET saldo = saldo + %s WHERE id = 1", (valor_add,))
    cur.execute("INSERT INTO historico (cliente_nome, valor_pago, detalhe) VALUES (%s, %s, %s)", ("CAIXA", valor_add, "Adição Manual"))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/historico')
def historico():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Busca os dados para a Tabela (os últimos 50 registros)
    cur.execute("SELECT * FROM historico ORDER BY data_pagamento DESC LIMIT 50")
    dados_tabela = cur.fetchall()
    
    # 2. Busca os dados para o Gráfico (Soma lucros agrupado por Mês)
    # TO_CHAR converte a data para '02/2026'
    cur.execute("""
        SELECT TO_CHAR(data_pagamento, 'MM/YYYY') as mes, SUM(valor_pago)
        FROM historico 
        WHERE valor_pago > 0 -- Pega só o que entrou (Lucro/Pagamentos)
        GROUP BY 1
        ORDER BY MAX(data_pagamento) ASC
        LIMIT 12 -- Mostra os últimos 12 meses
    """)
    dados_grafico = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # Prepara lista da Tabela
    lista_historico = []
    for linha in dados_tabela:
        lista_historico.append({
            "cliente": linha[1],
            "valor": linha[2],
            "data": linha[3].strftime('%d/%m/%Y %H:%M'),
            "detalhe": linha[4]
        })

    # Prepara listas do Gráfico para o JavaScript
    meses_grafico = []
    valores_grafico = []
    for linha in dados_grafico:
        meses_grafico.append(linha[0])    # Ex: '02/2026'
        valores_grafico.append(float(linha[1])) # Ex: 1250.00

    return render_template('historico.html', 
                           historico=lista_historico,
                           meses_grafico=meses_grafico,
                           valores_grafico=valores_grafico)


if __name__ == '__main__':
    app.run(debug=True)