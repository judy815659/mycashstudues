import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pytesseract
from PIL import Image
import re

# --- 1. データベース設定 ---
def init_db():
    conn = sqlite3.connect('kakeibo_v4.db')
    cursor = conn.cursor()
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

# --- 2. 画面設定 ---
st.set_page_config(page_title="My家計簿アプリ", layout="centered")
st.title("💰 Simple家計簿 & 支払い管理")

# --- 3. サイドバー入力 ---
with st.sidebar:
    st.header("新規入力")
    date = st.date_input("日付", datetime.now())
    t_type = st.radio("収支種別", ["支出", "収入"])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "固定費", "分割払", "給与", "その他"])
    
    # セッション状態の初期化
    if 'ocr_amount' not in st.session_state:
        st.session_state['ocr_amount'] = 0
    
    amount = st.number_input("金額 (円)", min_value=0, step=100, key="amount_input", value=st.session_state['ocr_amount'])
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "d払い", "デビットカード", "paydy"])

    # --- OCRセクション ---
    st.markdown("---")
    st.subheader("📷 レシート読み取り")
    uploaded_file = st.file_uploader("レシートを選択", type=['jpg', 'jpeg', 'png'])

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='アップロード画像', use_container_width=True)

    if st.button("文字を読み取る"):
            with st.spinner('解析中...'):
                try:
                    pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'
                    # 日本語と英語を混ぜて読み込み
                    raw_text = pytesseract.image_to_string(image, lang='jpn+eng')
                    
                    # 1. 読み取りテキストを整理
                    # 「¥」を「Y」や「S」と読み間違えることが多いので、これらを正規化
                    clean_text = raw_text.replace(',', '').replace(' ', '')
                    
                    # 2. 【新ロジック】「合計」「小計」「支払」「税込」という言葉の周辺にある数字を抽出
                    # 前後に 3〜5桁の数字（100円〜99,999円）がある箇所を狙う
                    pattern = r'(?:合計|小計|支払|税込|合計|金額|S|A|G|Y)[\D]*(\d{3,5})'
                    targets = re.findall(pattern, clean_text)
                    
                    # 3. 単純な3〜5桁の独立した数字も予備で拾う
                    backups = re.findall(r'\b\d{3,5}\b', clean_text)
                    
                    # 候補を合体
                    all_candidates = list(set(targets + backups))
                    
                    if all_candidates:
                        st.write("💰 **合計金額の候補：**")
                        # 合計金額はリストの中でも大きい方の数字であることが多いため、数値の大きい順に並べる
                        final_list = sorted(all_candidates, key=int, reverse=True)
                        
                        for num in final_list[:5]:
                            if st.button(f"¥{num} をセット"):
                                st.session_state['ocr_amount'] = int(num)
                                st.rerun()
                    else:
                        st.warning("金額が見つかりませんでした。")
                    
                    with st.expander("読み取り原文を表示"):
                        st.text(raw_text)
                except Exception as e:
                    st.error(f"エラー: {e}")
    # --- 分割払い設定 ---
    st.markdown("---")
    is_split = st.checkbox("分割払いにする")
    split_count = st.number_input("分割回数", min_value=2, max_value=60, value=2) if is_split else 1
    next_month = datetime.now() + relativedelta(months=1)
    pay_start_month = st.date_input("支払い開始月", next_month)

    if st.button("データを保存"):
        conn = init_db()
        cur = conn.cursor()
        per_month_amount = amount // split_count
        for i in range(split_count):
            current_pay_date = pay_start_month + relativedelta(months=i)
            p_month_str = current_pay_date.strftime('%Y-%m')
            cur.execute("INSERT INTO records (date, category, amount, method, type, payment_month) VALUES (?, ?, ?, ?, ?, ?)",
                        (date.strftime('%Y-%m-%d'), category, per_month_amount, method, t_type, p_month_str))
        conn.commit()
        st.session_state['ocr_amount'] = 0
        st.success("保存完了！")
        st.rerun()

    st.divider() 
    monthly_budget = st.number_input("今月の手取り給与", min_value=0, value=0, step=1000)

# --- 4. メイン表示 ---
conn = init_db()
df = pd.read_sql_query("SELECT * FROM records", conn)

if not df.empty:
    this_month_str = datetime.now().strftime('%Y-%m')
    df_this_month = df[df['date'].str.contains(this_month_str)]
    total_income = df_this_month[df_this_month['type'] == '収入']['amount'].sum()
    total_expense = df_this_month[df_this_month['type'] == '支出']['amount'].sum()
    
    st.header(f"📊 {this_month_str} の状況")
    col1, col2, col3 = st.columns(3)
    col1.metric("今月の収入", f"¥{total_income:,}")
    col2.metric("今月の支出", f"¥{total_expense:,}")
    col3.metric("残金", f"¥{total_income - total_expense:,}")

    if monthly_budget > 0:
        remaining = monthly_budget - total_expense
        st.info(f"💡 残り予算： **¥{remaining:,}**")
        percent = min(total_expense / monthly_budget, 1.0)
        st.progress(percent, text=f"予算の {percent*100:.1f}% を使用中")

    st.divider()
    st.header("🗓️ 支払い予定")
    all_months = sorted(df['payment_month'].unique(), reverse=True)
    view_month = st.selectbox("月を選択", all_months)
    month_df = df[df['payment_month'] == view_month]
    
    if not month_df.empty:
        summary = month_df.groupby('method')['amount'].sum()
        st.table(summary)
        st.warning(f"{view_month} の総支払額: **¥{summary.sum():,}**")
    
    st.subheader("履歴")
    st.dataframe(df.sort_values('date', ascending=False))
else:
    st.info("データがありません。")
