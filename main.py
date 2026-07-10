import sqlite3
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# 解決跨網域阻擋問題 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 4小時極速開發允許所有來源，實務上需指定網域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化 SQLite 資料庫
def init_db():
    conn = sqlite3.connect("gacha.db")
    cursor = conn.cursor()
    # 記帳資料表
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, amount INTEGER)''')
    # 使用者盲盒卡片表
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_cards 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, card_name TEXT, rarity TEXT)''')
    # 模擬使用者代幣（4小時專案暫存於記憶體，預設100代幣）
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_wallet 
                      (id INTEGER PRIMARY KEY, tokens INTEGER)''')
    cursor.execute('''INSERT OR IGNORE INTO user_wallet (id, tokens) VALUES (1, 100)''')
    conn.commit()
    conn.close()

init_db()

# 資料驗證模型 (Pydantic)
class ExpenseInput(BaseModel):
    item: str
    amount: int

@app.post("/api/expenses")
def add_expense(data: ExpenseInput):
    # 【資安防禦：輸入驗證】防止負數金額漏洞
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="金額必須大於 0")
    
    conn = sqlite3.connect("gacha.db")
    cursor = conn.cursor()
    
    # 【資安防禦：防止 SQL Injection】使用 ? 參數化查詢
    cursor.execute("INSERT INTO expenses (item, amount) VALUES (?, ?)", (data.item, data.amount))
    
    # 記帳成功，依金額比例回饋代幣（例如每10元換1代幣）
    earned_tokens = max(1, data.amount // 10)
    cursor.execute("UPDATE user_wallet SET tokens = tokens + ? WHERE id = 1", (earned_tokens,))
    
    conn.commit()
    conn.close()
    return {"message": "記帳成功", "earned_tokens": earned_tokens}

@app.get("/api/status")
def get_status():
    conn = sqlite3.connect("gacha.db")
    cursor = conn.cursor()
    cursor.execute("SELECT tokens FROM user_wallet WHERE id = 1")
    tokens = cursor.fetchone()[0]
    
    cursor.execute("SELECT item, amount FROM expenses ORDER BY id DESC")
    expenses = [{"item": row[0], "amount": row[1]} for row in cursor.fetchall()]
    conn.close()
    return {"tokens": tokens, "expenses": expenses}

@app.post("/api/gacha")
def draw_gacha():
    conn = sqlite3.connect("gacha.db")
    cursor = conn.cursor()
    cursor.execute("SELECT tokens FROM user_wallet WHERE id = 1")
    tokens = cursor.fetchone()[0]
    
    # 【資安防禦：後端驗證】防止前端修改代幣作弊
    if tokens < 20:
        conn.close()
        raise HTTPException(status_code=400, detail="代幣不足，抽一次需要 20 代幣！")
    
    # 扣除代幣
    cursor.execute("UPDATE user_wallet SET tokens = tokens - 20 WHERE id = 1")
    
    # 【資安防禦：後端計算隨機機率】防範前端竄改中獎率
    pool = [
        {"name": "SSR 頂級省錢大師卡", "rarity": "SSR", "weight": 5},
        {"name": "SR 節約小能手卡", "rarity": "SR", "weight": 25},
        {"name": "R 平凡打工人卡", "rarity": "R", "weight": 70}
    ]
    # 依權重隨機抽卡
    result = random.choices(pool, weights=[p["weight"] for p in pool], k=1)[0]
    
    cursor.execute("INSERT INTO user_cards (card_name, rarity) VALUES (?, ?)", (result["name"], result["rarity"]))
    conn.commit()
    conn.close()
    return {"card_name": result["name"], "rarity": result["rarity"]}

# 啟動指令：uvicorn main:app --reload