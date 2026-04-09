import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

# --- 1. スプレッドシート接続設定 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    return conn.read(ttl=0)

# --- 2. 画面設定 ---
st.set_page_config(page_title="My家計簿アプリ", layout="wide")
st.title("💰 スプシ連携・家計簿アプリ")

# --- 3. サイドバー入力 ---
with st.sidebar:
    st.header("新規入力")
    if 'ocr_amount' not in st.session_state: st.session_state['ocr_amount'] = 0
    if 'ocr_date' not in st.session_state: st.session_state['ocr_date'] = datetime.now()
    if 'ocr_memo' not in st.session_state: st.session_state['ocr_memo'] = ""

    target_date = st.date_input("日付", value=st.session_state['ocr_date'])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "医療費", "交通費", "固定費", "分割払", "給与", "その他"])
    t_type = st.radio("収支種別", ["支出", "収入"], index=1 if category == "給与" else 0)
    amount = st.number_input("金額 (円)", min_value=0, step=100, value=st.session_state['ocr_amount'])
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "Paydy(後払い)", "d払い", "デビットカード"])
    
    pay_month = st.text_input("支払い月 (YYYY-MM)", value=target_date.strftime('%Y-%m'))
    memo = st.text_area("備考（メモ）", value=st.session_state['ocr_memo'])
    is_calc = st.checkbox("今月の収支集計に含める", value=True)

    if st.button("💾 スプシへ保存"):
        try:
            df_current = get_data()
            new_row = pd.DataFrame([{
                "date": target_date.strftime('%Y-%m-%d'),
                "category": category,
                "amount": amount,
                "method": method,
                "type": t_type,
                "payment_month": pay_month,
                "memo": memo,
                "is_calc": 1 if is_calc else 0
            }])
            updated_df = pd.concat([df_current, new_row], ignore_index=True)
            conn.update(data=updated_df)
            st.success("保存完了！")
            st.session_state['ocr_amount'] = 0
            st.rerun()
        except Exception as e:
            st.error(f"保存失敗: {e}")

# --- 4. メイン表示 ---
df = get_data()

if df is not None and not df.empty:
    # --- 1. 型変換を徹底（ここがズレていると金額が合わなくなります） ---
    df = df.copy() # 警告防止
    
    # 金額：文字が入っていても無理やり数値にする
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0).astype(int)
    
    # チェックボックス：1, "1", True, "TRUE" をすべて「集計対象」として認める
    def cleanup_bool(x):
        if str(x).upper() in ["TRUE", "1", "1.0", "YES"]: return 1
        return 0
    df['is_calc_clean'] = df['is_calc'].apply(cleanup_bool)
    
    # 日付：パースに失敗しても壊れないようにする
    df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_key'] = df['date_dt'].dt.strftime('%Y-%m')
    
    # 支払い月：スペースを消してハイフンに統一
    df['pay_month_clean'] = df['payment_month'].astype(str).str.replace('/', '-').str.strip()

    # --- 2. 表示月の選択 ---
    available_months = sorted(df['month_key'].dropna().unique(), reverse=True)
    if not available_months: # もし日付が1つも取れなかった場合の予備
        available_months = [datetime.now().strftime('%Y-%m')]
    selected_month = st.selectbox("表示する月を選択してください", available_months)

    # --- 3. 厳密な集計 ---
    # 【実支出】
    # 条件：1. 発生月が選択月 2. 支出である 3. 集計対象フラグが立っている
    df_actual = df[
        (df['month_key'] == selected_month) & 
        (df['type'].str.contains('支出')) & 
        (df['is_calc_clean'] == 1)
    ]
    total_actual = int(df_actual['amount'].sum())

    # 【引落予定】
    # 条件：1. 支払い指定月が選択月 2. 支出である
    df_pay = df[
        (df['pay_month_clean'] == selected_month) & 
        (df['type'].str.contains('支出'))
    ]
    total_pay = int(df_pay['amount'].sum())

    # --- 4. 表示 ---
    col1, col2 = st.columns(2)
    col1.metric(f"📊 {selected_month} の実支出", f"¥{total_actual:,}")
    col2.metric(f"📅 {selected_month} の引落予定", f"¥{total_pay:,}")
    
    # (この下にタブや履歴一覧を続ける)
