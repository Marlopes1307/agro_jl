import sqlite3
import webbrowser
import threading
import time
import hashlib
import sys
import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
from database import criar_banco

app = FastAPI(title="Agro J&L PDV")

def caminho_recurso(relativo):
    # Encontra a pasta correta tanto rodando no Python quanto dentro do .exe
    base = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base, relativo)

# Garante que o banco existe ao iniciar
criar_banco()

def get_db():
    conn = sqlite3.connect('agro_jl.db')
    conn.row_factory = sqlite3.Row
    return conn

class ItemVendaSchema(BaseModel):
    produto_id: int
    quantidade: float
    preco_unitario: float
    subtotal: float

class VendaSchema(BaseModel):
    vendedor_nome: str
    cliente_nome: Optional[str] = ""
    eh_entrega: bool = False
    observacao: Optional[str] = ""
    subtotal: float
    desconto: float = 0.0
    total: float
    forma_pagamento: str
    valor_recebido: float = 0.0
    troco: float = 0.0
    itens: List[ItemVendaSchema]

# Rota Principal: Abre a tela do PDV diretamente
@app.get("/")
async def pagina_login():
    return FileResponse(caminho_recurso("templates/login.html"))

@app.get("/pdv")
async def pagina_pdv():
    return FileResponse(caminho_recurso("templates/pdv.html"))

@app.get("/produtos")
async def pagina_produtos():
    return FileResponse(caminho_recurso("templates/produtos.html"))

@app.get("/caixa")
async def pagina_caixa():
    return FileResponse(caminho_recurso("templates/caixa.html"))

@app.get("/relatorios")
async def pagina_relatorios():
    return FileResponse(caminho_recurso("templates/relatorios.html"))

@app.get("/clientes")
async def pagina_clientes():
    return FileResponse(caminho_recurso("templates/clientes.html"))


# API: Buscar Produto por Código de Barras ou Nome
@app.get("/api/produtos/buscar")
def buscar_produto(termo: str):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM produtos WHERE codigo_barras = ?", (termo.strip(),))
    produto = cursor.fetchone()
    
    if produto:
        conn.close()
        return [dict(produto)]
    
    cursor.execute("SELECT * FROM produtos WHERE nome LIKE ? LIMIT 10", (f"%{termo.strip()}%",))
    produtos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return produtos

# API: Finalizar Venda e Baixar Estoque
@app.post("/api/vendas")
def registrar_venda(venda: VendaSchema):
    if not venda.itens:
        raise HTTPException(status_code=400, detail="O carrinho está vazio.")

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id FROM caixas WHERE status = 'aberto' ORDER BY id DESC LIMIT 1")
        caixa = cursor.fetchone()
        if not caixa:
            raise HTTPException(status_code=400, detail="Nenhum caixa aberto no momento.")
        caixa_id = caixa["id"]

        cursor.execute('''
            INSERT INTO vendas (
                caixa_id, vendedor_nome, cliente_nome, eh_entrega, observacao,
                subtotal, desconto, total, forma_pagamento, valor_recebido, troco
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            caixa_id, venda.vendedor_nome, venda.cliente_nome,
            1 if venda.eh_entrega else 0, venda.observacao,
            venda.subtotal, venda.desconto, venda.total,
            venda.forma_pagamento, venda.valor_recebido, venda.troco
        ))
        venda_id = cursor.lastrowid

        for item in venda.itens:
            cursor.execute('''
                INSERT INTO itens_venda (venda_id, produto_id, quantidade, preco_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?)
            ''', (venda_id, item.produto_id, item.quantidade, item.preco_unitario, item.subtotal))

            cursor.execute('''
                UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE id = ?
            ''', (item.quantidade, item.produto_id))

        conn.commit()
        return {"mensagem": "Venda registrada com sucesso!", "venda_id": venda_id}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
        # --- NOVAS ROTAS PARA PRODUTOS & GRANEL ---

class ProdutoSchema(BaseModel):
    codigo_barras: str
    nome: str
    categoria: Optional[str] = "Geral"
    unidade: str
    preco_custo: float
    preco_venda: float
    estoque_atual: float
    estoque_minimo: float = 3.0
    data_validade: Optional[str] = None

class ConversaoGranelSchema(BaseModel):
    saco_id: int
    granel_id: int
    peso_kg: float

@app.get("/produtos")
async def pagina_produtos():
    return FileResponse("templates/produtos.html")

@app.get("/api/produtos")
def listar_produtos():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM produtos ORDER BY nome ASC")
    produtos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return produtos

@app.post("/api/produtos")
def criar_produto(prod: ProdutoSchema):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO produtos (codigo_barras, nome, categoria, unidade, preco_custo, preco_venda, estoque_atual, estoque_minimo, data_validade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (prod.codigo_barras, prod.nome, prod.categoria, prod.unidade, prod.preco_custo, prod.preco_venda, prod.estoque_atual, prod.estoque_minimo, prod.data_validade))
        conn.commit()
        return {"mensagem": "Produto cadastrado com sucesso!"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Já existe um produto com este código de barras.")
    finally:
        conn.close()

@app.put("/api/produtos/{produto_id}")
def atualizar_produto(produto_id: int, prod: ProdutoSchema):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE produtos SET codigo_barras=?, nome=?, categoria=?, unidade=?, preco_custo=?, preco_venda=?, estoque_atual=?, estoque_minimo=?, data_validade=?
            WHERE id=?
        ''', (prod.codigo_barras, prod.nome, prod.categoria, prod.unidade, prod.preco_custo, prod.preco_venda, prod.estoque_atual, prod.estoque_minimo, prod.data_validade, produto_id))
        conn.commit()
        return {"mensagem": "Produto atualizado!"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Código de barras já utilizado em outro produto.")
    finally:
        conn.close()

@app.delete("/api/produtos/{produto_id}")
def deletar_produto(produto_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM produtos WHERE id=?", (produto_id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Produto removido."}

@app.post("/api/produtos/converter-granel")
def converter_saco_granel(dados: ConversaoGranelSchema):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT estoque_atual FROM produtos WHERE id=?", (dados.saco_id,))
        saco = cursor.fetchone()
        if not saco or saco["estoque_atual"] < 1:
            raise HTTPException(status_code=400, detail="Estoque insuficiente do saco fechado.")

        cursor.execute("UPDATE produtos SET estoque_atual = estoque_atual - 1 WHERE id=?", (dados.saco_id,))
        cursor.execute("UPDATE produtos SET estoque_atual = estoque_atual + ? WHERE id=?", (dados.peso_kg, dados.granel_id))
        conn.commit()
        return {"mensagem": "Conversão realizada com sucesso!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
        
        # --- NOVAS ROTAS PARA CONTROLE DE CAIXA ---

class AbrirCaixaSchema(BaseModel):
    valor_inicial: float

class MovimentacaoCaixaSchema(BaseModel):
    tipo: str
    valor: float
    motivo: str

class FecharCaixaSchema(BaseModel):
    valor_informado: float

@app.get("/caixa")
async def pagina_caixa():
    return FileResponse("templates/caixa.html")

@app.get("/api/caixa/atual")
def status_caixa_atual():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM caixas WHERE status = 'aberto' ORDER BY id DESC LIMIT 1")
    caixa = cursor.fetchone()
    
    if not caixa:
        conn.close()
        return {"aberto": False}
    
    caixa_dict = dict(caixa)
    caixa_id = caixa_dict["id"]

    # Soma vendas por forma de pagamento neste caixa
    cursor.execute('''
        SELECT forma_pagamento, COALESCE(SUM(total), 0) as total
        FROM vendas WHERE caixa_id = ? GROUP BY forma_pagamento
    ''', (caixa_id,))
    vendas_pgto = {row["forma_pagamento"]: row["total"] for row in cursor.fetchall()}

    # Soma suprimentos e sangrias
    cursor.execute('''
        SELECT tipo, COALESCE(SUM(valor), 0) as total
        FROM movimentacoes_caixa WHERE caixa_id = ? GROUP BY tipo
    ''', (caixa_id,))
    movs = {row["tipo"]: row["total"] for row in cursor.fetchall()}

    # Lista histórico de movimentações
    cursor.execute("SELECT * FROM movimentacoes_caixa WHERE caixa_id = ? ORDER BY id DESC", (caixa_id,))
    historico_movs = [dict(row) for row in cursor.fetchall()]

    dinheiro_vendas = vendas_pgto.get("Dinheiro", 0.0)
    suprimentos = movs.get("suprimento", 0.0)
    sangrias = movs.get("sangria", 0.0)
    saldo_gaveta_esperado = caixa_dict["valor_inicial"] + dinheiro_vendas + suprimentos - sangrias

    conn.close()
    return {
        "aberto": True,
        "caixa": caixa_dict,
        "vendas_pgto": vendas_pgto,
        "suprimentos": suprimentos,
        "sangrias": sangrias,
        "saldo_gaveta_esperado": saldo_gaveta_esperado,
        "historico_movs": historico_movs
    }

@app.post("/api/caixa/abrir")
def abrir_caixa(dados: AbrirCaixaSchema):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM caixas WHERE status = 'aberto'")
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Já existe um caixa aberto!")
    
    cursor.execute("INSERT INTO caixas (usuario_id, valor_inicial, status) VALUES (1, ?, 'aberto')", (dados.valor_inicial,))
    conn.commit()
    conn.close()
    return {"mensagem": "Caixa aberto com sucesso!"}

@app.post("/api/caixa/movimentacao")
def registrar_movimentacao(dados: MovimentacaoCaixaSchema):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM caixas WHERE status = 'aberto' ORDER BY id DESC LIMIT 1")
    caixa = cursor.fetchone()
    if not caixa:
        conn.close()
        raise HTTPException(status_code=400, detail="Nenhum caixa aberto.")
    
    cursor.execute('''
        INSERT INTO movimentacoes_caixa (caixa_id, tipo, valor, motivo)
        VALUES (?, ?, ?, ?)
    ''', (caixa["id"], dados.tipo, dados.valor, dados.motivo))
    conn.commit()
    conn.close()
    return {"mensagem": "Movimentação registrada!"}

@app.post("/api/caixa/fechar")
def fechar_caixa(dados: FecharCaixaSchema):
    status = status_caixa_atual()
    if not status["aberto"]:
        raise HTTPException(status_code=400, detail="Nenhum caixa aberto para fechar.")
    
    caixa_id = status["caixa"]["id"]
    esperado = status["saldo_gaveta_esperado"]
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE caixas 
        SET status = 'fechado', data_fechamento = CURRENT_TIMESTAMP, 
            valor_final_sistema = ?, valor_final_informado = ?
        WHERE id = ?
    ''', (esperado, dados.valor_informado, caixa_id))
    conn.commit()
    conn.close()
    return {"mensagem": "Caixa fechado com sucesso!", "diferenca": dados.valor_informado - esperado}

# --- NOVAS ROTAS PARA RELATÓRIOS & USUÁRIOS ---

class LoginSchema(BaseModel):
    login: str
    senha: str

class NovoUsuarioSchema(BaseModel):
    nome: str
    login: str
    senha: str
    perfil: str

@app.get("/relatorios")
async def pagina_relatorios():
    return FileResponse("templates/relatorios.html")

@app.post("/api/login")
def autenticar_usuario(dados: LoginSchema):
    conn = get_db()
    cursor = conn.cursor()
    senha_hash = hashlib.sha256(dados.senha.encode()).hexdigest()
    cursor.execute("SELECT id, nome, login, perfil FROM usuarios WHERE login = ? AND senha = ?", (dados.login, senha_hash))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Login ou senha incorretos.")
    return dict(user)

@app.get("/api/usuarios")
def listar_usuarios():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, login, perfil FROM usuarios ORDER BY nome ASC")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

@app.post("/api/usuarios")
def criar_usuario(dados: NovoUsuarioSchema):
    conn = get_db()
    cursor = conn.cursor()
    senha_hash = hashlib.sha256(dados.senha.encode()).hexdigest()
    try:
        cursor.execute("INSERT INTO usuarios (nome, login, senha, perfil) VALUES (?, ?, ?, ?)",
                       (dados.nome, dados.login, senha_hash, dados.perfil))
        conn.commit()
        return {"mensagem": "Usuário cadastrado com sucesso!"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Este login já está em uso.")
    finally:
        conn.close()

@app.get("/api/relatorios/resumo")
def obter_resumo_relatorios(data_inicio: str, data_fim: str):
    conn = get_db()
    cursor = conn.cursor()

    # 1. Faturamento Bruto, Descontos e Quantidade de Vendas no período
    cursor.execute('''
        SELECT COUNT(*) as qtd_vendas,
               COALESCE(SUM(total), 0) as faturamento,
               COALESCE(SUM(desconto), 0) as total_descontos
        FROM vendas
        WHERE DATE(data_hora) BETWEEN ? AND ?
    ''', (data_inicio, data_fim))
    resumo_vendas = dict(cursor.fetchone())

    # 2. Custo dos produtos vendidos para calcular Lucro Bruto Estimado
    cursor.execute('''
        SELECT COALESCE(SUM(iv.quantidade * p.preco_custo), 0) as custo_total
        FROM itens_venda iv
        JOIN vendas v ON iv.venda_id = v.id
        JOIN produtos p ON iv.produto_id = p.id
        WHERE DATE(v.data_hora) BETWEEN ? AND ?
    ''', (data_inicio, data_fim))
    custo_total = cursor.fetchone()["custo_total"]
    resumo_vendas["lucro_estimado"] = resumo_vendas["faturamento"] - custo_total

    # 3. Ranking por Vendedor
    cursor.execute('''
        SELECT vendedor_nome, COUNT(*) as qtd, COALESCE(SUM(total), 0) as total
        FROM vendas
        WHERE DATE(data_hora) BETWEEN ? AND ?
        GROUP BY vendedor_nome
        ORDER BY total DESC
    ''', (data_inicio, data_fim))
    por_vendedor = [dict(row) for row in cursor.fetchall()]

    # 4. Últimas 20 Vendas detalhadas
    cursor.execute('''
        SELECT id, strftime('%d/%m/%Y %H:%M', data_hora) as data_formatada,
               vendedor_nome, cliente_nome, eh_entrega, forma_pagamento, total
        FROM vendas
        WHERE DATE(data_hora) BETWEEN ? AND ?
        ORDER BY id DESC LIMIT 20
    ''', (data_inicio, data_fim))
    ultimas_vendas = [dict(row) for row in cursor.fetchall()]
    # 5. Produtos Mais Vendidos no Período
    cursor.execute('''
        SELECT p.nome, p.unidade,
               COALESCE(SUM(iv.quantidade), 0) as qtd_vendida,
               COALESCE(SUM(iv.subtotal), 0) as total_faturado
        FROM itens_venda iv
        JOIN vendas v ON iv.venda_id = v.id
        JOIN produtos p ON iv.produto_id = p.id
        WHERE DATE(v.data_hora) BETWEEN ? AND ?
        GROUP BY p.id, p.nome, p.unidade
        ORDER BY total_faturado DESC
        LIMIT 15
    ''', (data_inicio, data_fim))
    mais_vendidos = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {
        "resumo": resumo_vendas,
        "por_vendedor": por_vendedor,
        "ultimas_vendas": ultimas_vendas,
        "mais_vendidos": mais_vendidos
    }

    # --- NOVAS ROTAS PARA CLIENTES & PETS ---

class ClienteSchema(BaseModel):
    nome: str
    telefone: Optional[str] = ""
    cpf: Optional[str] = ""
    endereco: Optional[str] = ""
    nome_pet: Optional[str] = ""
    especie_pet: Optional[str] = ""
    observacoes: Optional[str] = ""

@app.get("/clientes")
async def pagina_clientes():
    return FileResponse("templates/clientes.html")

@app.get("/api/clientes")
def listar_clientes():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes ORDER BY nome ASC")
    clientes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return clientes

@app.post("/api/clientes")
def criar_cliente(cli: ClienteSchema):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO clientes (nome, telefone, cpf, endereco, nome_pet, especie_pet, observacoes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (cli.nome, cli.telefone, cli.cpf, cli.endereco, cli.nome_pet, cli.especie_pet, cli.observacoes))
    conn.commit()
    conn.close()
    return {"mensagem": "Cliente cadastrado com sucesso!"}

@app.put("/api/clientes/{cliente_id}")
def atualizar_cliente(cliente_id: int, cli: ClienteSchema):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE clientes SET nome=?, telefone=?, cpf=?, endereco=?, nome_pet=?, especie_pet=?, observacoes=?
        WHERE id=?
    ''', (cli.nome, cli.telefone, cli.cpf, cli.endereco, cli.nome_pet, cli.especie_pet, cli.observacoes, cliente_id))
    conn.commit()
    conn.close()
    return {"mensagem": "Cliente atualizado!"}

@app.delete("/api/clientes/{cliente_id}")
def deletar_cliente(cliente_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clientes WHERE id=?", (cliente_id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Cliente removido."}


def abrir_navegador():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    threading.Thread(target=abrir_navegador, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)
