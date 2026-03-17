import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- データベースの初期設定 ---
def init_db():
    conn = sqlite3.connect('kakeibo_new2.db')
    cursor = conn.cursor()
    # payment_month (支払い月) を追加して作成
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            category TEXT,
            amount INTEGER,
            method TEXT,
            type TEXT,
            payment_month TEXT
        )
    ''')
    conn.commit()
    return conn

# --- メイン処理 ---
st.set_page_config(page_title="My家計簿アプリ", layout="centered")
st.title("💰 Simple家計簿 & 支払い管理")

# 入力フォーム
with st.sidebar:
    st.header("新規入力")
    date = st.date_input("日付", datetime.now())
    t_type = st.radio("収支種別", ["支出", "収入"])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "固定費", "分割払", "給与", "その他"])
    amount = st.number_input("金額 (円)", min_value=0, step=100)
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "d払い", "デビットカード", "paydy"])

import pytesseract # 追加
from PIL import Image # 追加

# --- サイドバーの入力フォームの中に追記 ---
st.subheader("📷 レシート読み取り")
uploaded_file = st.file_uploader("レシートを撮影または選択", type=['jpg', 'jpeg', 'png'])

if uploaded_file is not None:
    # 画像を開く
    image = Image.open(uploaded_file)
    st.image(image, caption='アップロードされたレシート', use_column_width=True)
    
    if st.button("文字を読み取る"):
        # OCR実行（日本語と英語を指定）
        with st.spinner('解析中...'):
            try:
                text = pytesseract.image_to_string(image, lang='jpn')
                st.text_area("読み取り結果", text, height=200)
                st.info("💡 このテキストから「金額」などをコピーして入力欄に使ってください。")
            except Exception as e:
                st.error("OCRエンジンの準備ができていないようです。")
    
    # --- 分割払いや支払い月の設定 ---
    st.markdown("---")
    is_split = st.checkbox("分割払いにする")
    if is_split:
        split_count = st.number_input("分割回数", min_value=2, max_value=60, value=2)
    else:
        split_count = 1
        
    # 支払い開始月の設定（デフォルトは来月）
    next_month = datetime.now() + relativedelta(months=1)
    pay_start_month = st.date_input("支払い開始月（日付けは1日でOK）", next_month)

    if st.button("データを保存"):
        conn = init_db()
        cur = conn.cursor()
        
        # 分割払いの場合は回数分ループして保存
        per_month_amount = amount // split_count
        for i in range(split_count):
            current_pay_date = pay_start_month + relativedelta(months=i)
            p_month_str = current_pay_date.strftime('%Y-%m') # "2026-04" 形式
            
            cur.execute("INSERT INTO records (date, category, amount, method, type, payment_month) VALUES (?, ?, ?, ?, ?, ?)",
                        (date.strftime('%Y-%m-%d'), category, per_month_amount, method, t_type, p_month_str))
        
        conn.commit()
        st.success(f"保存完了！({'分割保存' if is_split else '通常保存'})")

# --- 予算設定のサイドバー ---
with st.sidebar:
    st.divider() 
    monthly_budget = st.number_input("今月の手取り給与", min_value=0, value=0, step=1000)

# データの表示・分析
conn = init_db()
df = pd.read_sql_query("SELECT * FROM records", conn)

if not df.empty:
    # 1. 今月の収支計算 (購入日ベース)
    this_month_str = datetime.now().strftime('%Y-%m')
    df_this_month = df[df['date'].str.contains(this_month_str)]
    
    total_income = df_this_month[df_this_month['type'] == '収入']['amount'].sum()
    total_expense = df_this_month[df_this_month['type'] == '支出']['amount'].sum()
    
    st.header(f"📊 {this_month_str} の状況")
    col1, col2, col3 = st.columns(3)
    col1.metric("今月の収入", f"¥{total_income:,}")
    col2.metric("今月の支出", f"¥{total_expense:,}")
    col3.metric("残金", f"¥{total_income - total_expense:,}")

    # 予算に対する使用率のプログレスバー
    if monthly_budget > 0:
        remaining = monthly_budget - total_expense
        st.info(f"💡 今月の残り予算： **¥{remaining:,}**")
        percent = min(total_expense / monthly_budget, 1.0)
        st.progress(percent, text=f"予算の {percent*100:.1f}% を使用中")

    # 2. 【新機能】月別の支払い予定
    st.divider()
    st.header("🗓️ 支払い予定（引き落としベース）")
    
    # 表示したい月を選択
    view_month = st.selectbox("確認したい支払い月", sorted(df['payment_month'].unique(), reverse=True))
    month_df = df[df['payment_month'] == view_month]
    
    if not month_df.empty:
        summary = month_df.groupby('method')['amount'].sum()
        st.table(summary)
        st.warning(f"{view_month} の総支払予定額: **¥{summary.sum():,}**")
    
    # グラフ表示
    st.subheader("カテゴリ別支出分析")
    expense_df = df[df['type'] == '支出']
    if not expense_df.empty:
        st.bar_chart(expense_df.groupby('category')['amount'].sum())

    # 履歴一覧
    st.subheader("全履歴一覧")
    st.dataframe(df.sort_values('date', ascending=False))
else:
    st.info("データがありません。左から入力してください。")
