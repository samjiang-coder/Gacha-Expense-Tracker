import sqlite3  # SQLite 是內建的輕量級資料庫，就像一個簡單的 Excel 表格檔案，用來儲存資料
import random  # 隨機模組，用來做抽卡時的「擲骰子」隨機決定機率
from fastapi import FastAPI, HTTPException  # FastAPI 是用來蓋後端伺服器的工具；HTTPException 則用來回傳「錯誤訊息」給前端（例如代幣不足）
from fastapi.middleware.cors import CORSMiddleware  # CORS 門神，用來允許不同網址的網頁（前端）可以向我們的伺服器（後端）要資料
from pydantic import BaseModel  # Pydantic 像一個「驗證信箱」，用來規定前端寄過來的資料格式必須正確，不能亂寄

app = FastAPI()

# 解決跨網域阻擋問題 (CORS)
# 就像是在校門口貼一張公告：「歡迎所有人進來參觀」，這樣網頁才能順利連上這台伺服器取得資料
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 4小時極速開發允許所有來源，實務上需指定網域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化 SQLite 資料庫
# 就像是在開學前先把教室裡的課桌椅（資料表）擺好，並在錢包裡放一些零用錢
def init_db():
    conn = sqlite3.connect("gacha.db")  # 連接到資料庫檔案，如果檔案不存在會自動生出來
    cursor = conn.cursor()  # cursor 就像是畫筆，我們用它來對資料庫下指令
    # 記帳資料表
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, amount INTEGER)''')
    # 使用者盲盒卡片表
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_cards 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, card_name TEXT, rarity TEXT)''')
    # 模擬使用者代幣（4小時專案暫存於記憶體，預設100代幣）
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_wallet 
                      (id INTEGER PRIMARY KEY, tokens INTEGER)''')
    # 如果是第一次執行，先給玩家 100 代幣（零用錢）當作初始金
    cursor.execute('''INSERT OR IGNORE INTO user_wallet (id, tokens) VALUES (1, 100)''')
    conn.commit()  # 存檔存起來！
    conn.close()  # 用完要把連線關掉，才不會佔用資源

init_db()

# 資料驗證模型 (Pydantic)
# 這邊規定了「記帳」的格式，就像一張表單，一定要寫「品項（文字）」和「金額（整數）」這兩欄，少一欄或打錯字就會被退件
class ExpenseInput(BaseModel):
    item: str
    amount: int

# 新增記帳的 API，前端網頁送出記帳後會執行這裡
@app.post("/api/expenses")
def add_expense(data: ExpenseInput):
    # 【資安防禦：輸入驗證】防止負數金額漏洞
    # 如果使用者故意輸入金額是負的（例如 -100），我們得把它擋掉，不然他反而會被扣錢或者洗錢！
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="金額必須大於 0")
    
    conn = sqlite3.connect("gacha.db")
    cursor = conn.cursor()
    
    # 【資安防禦：防止 SQL Injection】使用 ? 參數化查詢
    # 用 ? 當作安全的預留位置，這樣可以防範駭客在輸入欄打入惡意的 SQL 指令來破壞資料庫
    cursor.execute("INSERT INTO expenses (item, amount) VALUES (?, ?)", (data.item, data.amount))
    
    # 記帳成功，依金額比例回饋代幣（例如每10元換1代幣）
    # 如果買了 50 元的午餐，就可以拿到 5 代幣；如果太省只花 5 元，也至少送 1 代幣！
    earned_tokens = max(1, data.amount // 10)
    # 把回饋的代幣加進皮夾（user_wallet）中
    cursor.execute("UPDATE user_wallet SET tokens = tokens + ? WHERE id = 1", (earned_tokens,))
    
    conn.commit()
    conn.close()
    return {"message": "記帳成功", "earned_tokens": earned_tokens}

# 取得當前狀態的 API，用來回傳剩多少代幣和所有記帳紀錄，讓前端網頁畫面可以更新
@app.get("/api/status")
def get_status():
    conn = sqlite3.connect("gacha.db")
    cursor = conn.cursor()
    # 從皮夾抓出當前的代幣餘額
    cursor.execute("SELECT tokens FROM user_wallet WHERE id = 1")
    tokens = cursor.fetchone()[0]
    
    # 從記帳表拉出所有的記帳歷史（照最新時間排序）
    cursor.execute("SELECT item, amount FROM expenses ORDER BY id DESC")
    expenses = [{"item": row[0], "amount": row[1]} for row in cursor.fetchall()]
    conn.close()
    return {"tokens": tokens, "expenses": expenses}

# 抽盲盒卡片的 API，前端按下抽卡按鈕時會跑來這裡
@app.post("/api/gacha")
def draw_gacha():
    conn = sqlite3.connect("gacha.db")
    cursor = conn.cursor()
    cursor.execute("SELECT tokens FROM user_wallet WHERE id = 1")
    tokens = cursor.fetchone()[0]
    
    # 【資安防禦：後端驗證】防止前端修改代幣作弊
    # 絕對要在後端重新檢查錢包！不能只相信前端，否則駭客改一下網頁程式碼就能免費抽卡了
    if tokens < 20:
        conn.close()
        raise HTTPException(status_code=400, detail="代幣不足，抽一次需要 20 代幣！")
    
    # 扣除代幣
    # 抽一次扣 20 元代幣，直接從皮夾資料扣除
    cursor.execute("UPDATE user_wallet SET tokens = tokens - 20 WHERE id = 1")
    
    # 【資安防禦：後端計算隨機機率】防範前端竄改中獎率
    # 抽卡池與中獎機率（權重），SSR 只有 5%、SR 有 25%、R 卡佔了 70%！
    pool = [
        {"name": "SSR 頂級省錢大師卡", "rarity": "SSR", "weight": 5},
        {"name": "SR 節約小能手卡", "rarity": "SR", "weight": 25},
        {"name": "R 平凡打工人卡", "rarity": "R", "weight": 70}
    ]
    # 依權重隨機抽卡
    # random.choices 就像是做一個有不同大小扇形的幸運轉盤，並轉動它
    result = random.choices(pool, weights=[p["weight"] for p in pool], k=1)[0]
    
    # 把抽到的卡片紀錄加到 user_cards 資料表（代表你收集到的卡片）
    cursor.execute("INSERT INTO user_cards (card_name, rarity) VALUES (?, ?)", (result["name"], result["rarity"]))
    conn.commit()
    conn.close()
    # 把抽中的卡片名稱和稀有度送回給前端顯示
    return {"card_name": result["name"], "rarity": result["rarity"]}

# 啟動指令：.venv\Scripts\uvicorn main:app --reload