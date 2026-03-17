import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

# --- 1. データベース設定 ---
def init_db():
    conn = sqlite3.connect('kakeibo_v5.db')
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
    
    # セッション状態（金額と日付の自動保持）
    if 'ocr_amount' not in st.session_state:
        st.session_state['ocr_amount'] = 0
    if 'ocr_date' not in st.session_state:
        st.session_state['ocr_date'] = datetime.now()

    date = st.date_input("日付", value=st.session_state['ocr_date'])
    t_type = st.radio("収支種別", ["支出", "収入"])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "固定費", "分割払", "給与", "その他"])
    
    amount = st.number_input("金額 (円)", min_value=0, step=100, key="amount_input", value=st.session_state['ocr_amount'])
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "d払い", "デビットカード", "paydy"])

    # --- コピペ抽出セクション ---
    st.markdown("---")
    st.subheader("📝 テキストから自動入力")
    st.caption("iPhoneの写真で文字をコピーして下に貼り付けてください")
    
    pasted_text = st.text_area("レシートのコピー内容", height=100, placeholder="ここにペースト...")

    if pasted_text:
        # 数字の抽出（カンマを除去して3〜6桁を抽出）
        clean_pasted = pasted_text.replace(',', '').replace(' ', '')
        found_amounts = re.findall(r'\b\d{3,6}\b', clean_pasted)
        
        # 日付の抽出（YYYY/MM/DD や MM月DD日 など）
        found_dates = re.findall(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', pasted_text)

        if found_amounts or found_dates:
            st.info("💡 抽出された情報を選択してください")
            
            # 金額ボタン（修正版：エラーを回避するシンプルな書き方）
            if found_amounts:
                st.write("金額：")
                # 重複を消して、数値の大きい順に並べる
                unique_amounts = sorted(list(set(found_amounts)), key=int, reverse=True)[:3]
                
                # ボタンを横に並べる設定（ここを修正しました）
                cols = st.columns(len(unique_amounts))
                for i, num in enumerate(unique_amounts):
                    with cols[i]:
                        if st.button(f"¥{num}"):
                            st.session_state['ocr_amount'] = int(num)
                            st.rerun()

            # 日付ボタン
            if found_dates:
                st.write("日付：")
                for d_str in list(set(found_dates))[:2]:
                    if st.button(f"📅 {d_str}"):
                        try:
                            # 形式を整理してdatetimeに変換
                            clean_d = d_str.replace('年', '-').replace('月', '-').replace('日', '')
                            st.session_state['ocr_date'] = pd.to_datetime(clean_d)
                            st.rerun()
                        except:
                            st.error("日付の読み込みに失敗しました")

    # --- 保存・分割払い設定（変更なし） ---
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
        # 保存後にリセット
        st.session_state['ocr_amount'] = 0
        st.session_state['ocr_date'] = datetime.now()
        st.success("保存完了！")
