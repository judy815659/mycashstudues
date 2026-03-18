import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

# --- 1. データベース設定（v8：is_calc列を追加） ---
def init_db():
    conn = sqlite3.connect('kakeibo_v8.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            category TEXT,
            amount INTEGER,
            method TEXT,
            type TEXT,
            payment_month TEXT,
            memo TEXT,
            is_calc INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    return conn

# --- 2. 画面設定 ---
st.set_page_config(page_title="My家計簿アプリ", layout="wide")
st.title("💰 Simple家計簿 & Paydy管理")

# --- 3. サイドバー入力 ---
with st.sidebar:
    st.header("新規入力")
    
    if 'ocr_amount' not in st.session_state: st.session_state['ocr_amount'] = 0
    if 'ocr_date' not in st.session_state: st.session_state['ocr_date'] = datetime.now()
    if 'ocr_memo' not in st.session_state: st.session_state['ocr_memo'] = ""

    # 入力項目
    target_date = st.date_input("日付", value=st.session_state['ocr_date'])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "固定費", "分割払", "給与", "その他"])
    
    t_type_index = 1 if category == "給与" else 0
    t_type = st.radio("収支種別", ["支出", "収入"], index=t_type_index)
    
    amount = st.number_input("金額 (円)", min_value=0, step=100, value=st.session_state['ocr_amount'])
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "Paydy(後払い)", "d払い", "デビットカード"])
    memo = st.text_area("備考（メモ）", value=st.session_state['ocr_memo'], placeholder="Amazonの注文内容など")

    # 【重要】収支スイッチ
    is_calc = st.checkbox("今月の収支集計に含める", value=True, help="Paydyの購入時など、記録だけ残して今月の残高を減らしたくない場合はオフにしてください")

    # --- コピペ抽出エリア ---
    st.markdown("---")
    st.subheader("📝 レシート・注文履歴から抽出")
    pasted_text = st.text_area("ここにコピー内容をペースト", height=80)

    if pasted_text:
        found_amounts = re.findall(r'\b\d{3,6}\b', pasted_text.replace(',', ''))
        date_patterns = [r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', r'(\d{1,2}月\d{1,2}日)']
        found_dates = []
        for p in date_patterns: found_dates.extend(re.findall(p, pasted_text))

        if found_amounts or found_dates or pasted_text:
            st.caption("クリックで反映：")
            if found_amounts:
                unique_amts = sorted(list(set(found_amounts)), key=int, reverse=True)[:3]
                cols = st.columns(len(unique_amts))
                for i, num in enumerate(unique_amts):
                    if cols[i].button(f"¥{num}"):
                        st.session_state['ocr_amount'] = int(num); st.rerun()
            if found_dates:
                for d_str in list(set(found_dates))[:2]:
                    if st.button(f"📅 {d_str}"):
                        clean_d = d_str.replace('年', '-').replace('月', '-').replace('日', '')
                        if '-' not in clean_d[:2]: clean_d = f"{datetime.now().year}-{clean_d}"
                        st.session_state['ocr_date'] = pd.to_datetime(clean_d); st.rerun()
            if st.button("📝 テキストを備考にコピー"):
                st.session_state['ocr_memo'] = pasted_text.replace('\n', ' ')[:100]; st.rerun()

    if st.button("💾 データを保存"):
        conn = init_db()
        cur = conn.cursor()
        save_date_str = target_date.strftime('%Y-%m-%d')
        cur.execute("""
            INSERT INTO records (date, category, amount, method, type, payment_month, memo, is_calc) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (save_date_str, category, amount, method, t_type, save_date_str[:7], memo, 1 if is_calc else 0))
        conn.commit()
        st.session_state['ocr_amount'] = 0; st.session_state['ocr_date'] = datetime.now(); st.session_state['ocr_memo'] = ""
        st.success("保存完了！"); st.rerun()

# --- 4. メイン表示 ---
conn = init_db()
df = pd.read_sql_query("SELECT id, date, category, amount, type, is_calc, memo, method FROM records ORDER BY date DESC", conn)

if not df.empty:
    this_month = datetime.now().strftime('%Y-%m')
    df_this_month = df[df['date'].str.contains(this_month)]
    
    # ★集計：is_calc が 1 のものだけを計算
    df_calc = df_this_month[df_this_month['is_calc'] == 1]
    total_expense = df_calc[df_calc['type'] == '支出']['amount'].sum()
    total_income = df_calc[df_calc['type'] == '収入']['amount'].sum()
    
    st.header(f"📊 {this_month} の収支（集計対象のみ）")
    c1, c2, c3 = st.columns(3)
    c1.metric("総収入", f"¥{total_income:,}")
    c2.metric("総支出", f"¥{total_expense:,}")
    c3.metric("今月の残り", f"¥{total_income - total_expense:,}")

    st.divider()
    st.subheader("履歴の管理（チェックして削除可能）")
    
    # 表示用の整形（is_calcを分かりやすく）
    display_df = df.copy()
    display_df['集計'] = display_df['is_calc'].apply(lambda x: "✅" if x == 1 else "記録のみ")
    
    edited_df = st.data_editor(
        display_df.drop(columns=['is_calc']),
        column_config={"id": None},
        disabled=["date", "category", "amount", "type", "memo", "method", "集計"],
        use_container_width=True,
        num_rows="dynamic"
    )

    if st.button("🗑️ 選択した行を削除する"):
        delete_ids = list(set(df["id"].tolist()) - set(edited_df["id"].tolist()))
        if delete_ids:
            cursor = conn.cursor()
            for d_id in delete_ids: cursor.execute("DELETE FROM records WHERE id = ?", (d_id,))
            conn.commit(); st.success("削除しました"); st.rerun()
else:
    st.info("データがありません。")
