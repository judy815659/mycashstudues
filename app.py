import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- データベースの初期設定 ---
def init_db():
    conn = sqlite3.connect('kakeibo.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            category TEXT,
            amount INTEGER,
            method TEXT,
            type TEXT
        )
    ''')
    conn.commit()
    return conn

# --- メイン処理 ---
st.set_page_config(page_title="My家計簿アプリ", layout="centered")
st.title("💰 Simple家計簿")

# 入力フォーム
with st.sidebar:
    st.header("新規入力")
    date = st.date_input("日付", datetime.now())
    t_type = st.radio("収支種別", ["支出", "収入"])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "固定費", "給与", "その他"])
    amount = st.number_input("金額 (円)", min_value=0, step=100)
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "d払い", "デビットカード", "paydy"])
    
    if st.button("データを保存"):
        conn = init_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO records (date, category, amount, method, type) VALUES (?, ?, ?, ?, ?)",
                    (date.strftime('%Y-%m-%d'), category, amount, method, t_type))
        conn.commit()
        st.success("保存完了！")

# データの表示・分析
conn = init_db()
df = pd.read_sql_query("SELECT * FROM records", conn)

if not df.empty:
    # 今月の収支計算
    total_income = df[df['type'] == '収入']['amount'].sum()
    total_expense = df[df['type'] == '支出']['amount'].sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("今月の収入", f"¥{total_income:,}")
    col2.metric("今月の支出", f"¥{total_expense:,}")
    col3.metric("残金", f"¥{total_income - total_expense:,}")

    # グラフ表示
    st.subheader("カテゴリ別支出推移")
    expense_df = df[df['type'] == '支出']
    if not expense_df.empty:
        st.bar_chart(expense_df.groupby('category')['amount'].sum())

    # 履歴一覧
    st.subheader("履歴一覧")
    st.dataframe(df.sort_values('date', ascending=False))
else:
    st.info("まだデータがありません。左のサイドバーから入力してください。")
# --- 予算設定のセクションを追加 ---
with st.sidebar:
    st.divider() # 区切り線
    monthly_budget = st.number_input("今月の手取り給与", min_value=0, value=0, step=1)

# --- 収支計算のロジックを強化 ---
if not df.empty:
    total_expense = df[df['type'] == '支出']['amount'].sum()
    remaining = monthly_budget - total_expense
    
    st.info(f"💡 今月の残り予算： **¥{remaining:,}**")
    
    # 予算に対する使用率のプログレスバー
    percent = min(total_expense / monthly_budget, 1.0)
    st.progress(percent, text=f"予算の {percent*100:.1f}% を使用中")
