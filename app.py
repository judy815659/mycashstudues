import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

# --- 1. データベース設定 ---
def init_db():
    conn = sqlite3.connect('kakeibo_v6.db')
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
    
    # セッション状態の初期化（未設定なら今日の日付と0円を入れる）
    if 'ocr_amount' not in st.session_state:
        st.session_state['ocr_amount'] = 0
    if 'ocr_date' not in st.session_state:
        st.session_state['ocr_date'] = datetime.now()

    # --- 入力項目 ---
    # カレンダー：デフォルトはセッション（今日 or コピペ反映）
    target_date = st.date_input("日付", value=st.session_state['ocr_date'])
    
    category_list = ["食費", "外食", "日用品", "娯楽", "固定費", "分割払", "給与", "その他"]
    category = st.selectbox("カテゴリ", category_list)
    
    # 給与なら「収入」へ自動切り替え
    t_type_index = 1 if category == "給与" else 0
    t_type = st.radio("収支種別", ["支出", "収入"], index=t_type_index)
    
    amount = st.number_input("金額 (円)", min_value=0, step=100, value=st.session_state['ocr_amount'])
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "d払い", "デビットカード", "paydy"])

    # --- コピペ抽出エリア ---
    st.markdown("---")
    st.subheader("📝 レシートから自動抽出")
    pasted_text = st.text_area("ここにコピー内容をペースト", height=80, placeholder="iPhoneでコピーした文字を貼り付け...")

    if pasted_text:
        # 数字（3〜6桁）と日付（YYYY/MM/DDやMM月DD日など）を探す
        found_amounts = re.findall(r'\b\d{3,6}\b', pasted_text.replace(',', ''))
        # 西友形式「3月16日」や「2026/03/16」に対応
        date_patterns = [r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', r'(\d{1,2}月\d{1,2}日)']
        found_dates = []
        for p in date_patterns:
            found_dates.extend(re.findall(p, pasted_text))

        if found_amounts or found_dates:
            st.caption("見つかった項目をクリックして反映：")
            
            # 金額ボタン
            if found_amounts:
                unique_amts = sorted(list(set(found_amounts)), key=int, reverse=True)[:3]
                cols = st.columns(len(unique_amts))
                for i, num in enumerate(unique_amts):
                    if cols[i].button(f"¥{num}"):
                        st.session_state['ocr_amount'] = int(num)
                        st.rerun()

            # 日付ボタン
            if found_dates:
                for d_str in list(set(found_dates))[:2]:
                    if st.button(f"📅 {d_str} を反映"):
                        try:
                            # 2026-03-16 形式に整えてセッション保存
                            clean_d = d_str.replace('年', '-').replace('月', '-').replace('日', '')
                            # 年が含まれない場合は今年の年を補完
                            if '-' not in clean_d[:2]:
                                clean_d = f"{datetime.now().year}-{clean_d}"
                            st.session_state['ocr_date'] = pd.to_datetime(clean_d)
                            st.rerun()
                        except:
                            st.error("日付の形式が合いませんでした")

    # --- 保存ボタン ---
    st.markdown("---")
    if st.button("💾 データを保存"):
        conn = init_db()
        cur = conn.cursor()
        
        # カレンダーで選ばれている日付（target_date）を保存
        save_date_str = target_date.strftime('%Y-%m-%d')
        
        cur.execute("""
            INSERT INTO records (date, category, amount, method, type, payment_month) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (save_date_str, category, amount, method, t_type, save_date_str[:7]))
        
        conn.commit()
        # 保存後に値をリセット
        st.session_state['ocr_amount'] = 0
        st.session_state['ocr_date'] = datetime.now()
        st.success(f"{save_date_str} のデータを保存しました！")
        st.rerun()

# --- 4. メイン表示 ---
conn = init_db()
df = pd.read_sql_query("SELECT * FROM records ORDER BY date DESC", conn)

if not df.empty:
    this_month = datetime.now().strftime('%Y-%m')
    df_this_month = df[df['date'].str.contains(this_month)]
    total_expense = df_this_month[df_this_month['type'] == '支出']['amount'].sum()
    
    st.header(f"📊 {this_month} の支出合計")
    st.metric("今月の総支出", f"¥{total_expense:,}")
    
    st.subheader("最近の履歴")
    # 履歴を編集・削除したい場合のために表示
    st.dataframe(df, use_container_width=True)
else:
    st.info("データがありません。")
