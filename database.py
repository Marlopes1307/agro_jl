import sqlite3
import hashlib

def criar_banco():
    conn = sqlite3.connect('agro_jl.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL CHECK(perfil IN ('admin', 'vendedor'))
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_barras TEXT UNIQUE,
            nome TEXT NOT NULL,
            categoria TEXT,
            unidade TEXT NOT NULL CHECK(unidade IN ('UN', 'KG')),
            preco_custo REAL NOT NULL,
            preco_venda REAL NOT NULL,
            estoque_atual REAL NOT NULL,
            estoque_minimo REAL DEFAULT 5,
            data_validade TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS caixas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            data_abertura DATETIME DEFAULT CURRENT_TIMESTAMP,
            valor_inicial REAL NOT NULL,
            data_fechamento DATETIME,
            valor_final_sistema REAL,
            valor_final_informado REAL,
            status TEXT DEFAULT 'aberto' CHECK(status IN ('aberto', 'fechado')),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caixa_id INTEGER,
            vendedor_nome TEXT,
            cliente_nome TEXT,
            eh_entrega INTEGER DEFAULT 0,
            observacao TEXT,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
            subtotal REAL NOT NULL,
            desconto REAL DEFAULT 0,
            total REAL NOT NULL,
            forma_pagamento TEXT NOT NULL,
            valor_recebido REAL DEFAULT 0,
            troco REAL DEFAULT 0,
            FOREIGN KEY (caixa_id) REFERENCES caixas(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            cpf TEXT,
            endereco TEXT,
            nome_pet TEXT,
            especie_pet TEXT,
            observacoes TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimentacoes_caixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caixa_id INTEGER,
            tipo TEXT NOT NULL CHECK(tipo IN ('suprimento', 'sangria')),
            valor REAL NOT NULL,
            motivo TEXT NOT NULL,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (caixa_id) REFERENCES caixas(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS itens_venda (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venda_id INTEGER,
            produto_id INTEGER,
            quantidade REAL NOT NULL,
            preco_unitario REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (venda_id) REFERENCES vendas(id),
            FOREIGN KEY (produto_id) REFERENCES produtos(id)
        )
    ''')
    # Inserir Admin Padrão (Login: admin | Senha: admin123)
    senha_admin = hashlib.sha256("admin123".encode()).hexdigest()
    cursor.execute('''
        INSERT OR IGNORE INTO usuarios (nome, login, senha, perfil)
        VALUES ('Administrador Agro J&L', 'admin', ?, 'admin')
    ''', (senha_admin,))

    # Inserir Vendedor Padrão (Login: vendedor | Senha: agrovendas)
    senha_vendedor = hashlib.sha256("agrovendas".encode()).hexdigest()
    cursor.execute('''
        INSERT OR IGNORE INTO usuarios (nome, login, senha, perfil)
        VALUES ('Vendedor Agro J&L', 'vendedor', ?, 'vendedor')
    ''', (senha_vendedor,))


    # Abre um caixa padrão caso não exista nenhum aberto
    cursor.execute("SELECT COUNT(*) FROM caixas WHERE status = 'aberto'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO caixas (usuario_id, valor_inicial, status) VALUES (1, 100.00, 'aberto')")

    produtos_exemplo = [
        ('78910001', 'Ração Golden Special Cães Adultos 15kg', 'Ração', 'UN', 120.00, 159.90, 10, 3, '2027-05-10'),
        ('20001', 'Ração Golden Cães Adultos (GRANEL)', 'Ração', 'KG', 8.00, 12.50, 30.0, 5.0, '2027-05-10'),
        ('78910002', 'Antipulgas Simparic 10 a 20kg', 'Medicamento', 'UN', 65.00, 95.00, 15, 4, '2027-01-15'),
        ('78910003', 'Coleira Antipulgas Gatos', 'Acessório', 'UN', 22.00, 45.00, 8, 2, None)
    ]
    cursor.executemany('''
        INSERT OR IGNORE INTO produtos (codigo_barras, nome, categoria, unidade, preco_custo, preco_venda, estoque_atual, estoque_minimo, data_validade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', produtos_exemplo)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    criar_banco()
