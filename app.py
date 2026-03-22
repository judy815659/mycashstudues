import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

# --- 1. スプレッドシート接続設定 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    # キャッシュを無効化して常に最新を取得
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
    
    # 【重要】支払い月の手動設定
    # デフォルトは入力した日付の月。Paydyならここを来月に書き換えて保存
    pay_month = st.text_input("支払い月 (YYYY-MM)", value=target_date.strftime('%Y-%m'))
    
    memo = st.text_area("備考（メモ）", value=st.session_state['ocr_memo'], placeholder="Amazonの注文内容など")
    is_calc = st.checkbox("今月の収支集計に含める", value=True)

    # --- テキスト抽出エリア ---
    st.markdown("---")
    pasted_text = st.text_area("ここにコピー内容をペースト", height=80)
    if pasted_text:
        found_amounts = re.findall(r'\b\d{3,6}\b', pasted_text.replace(',', ''))
        if found_amounts:
            st.caption("クリックで反映：")
            cols = st.columns(len(found_amounts[:3]))
            for i, num in enumerate(found_amounts[:3]):
                if cols[i].button(f"¥{num}"):
                    st.session_state['ocr_amount'] = int(num); st.rerun()

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
    # データ型の整理
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['payment_month'] = df['payment_month'].astype(str)
    df['date'] = df['date'].astype(str)
    
    today = datetime.now()
    this_month = today.strftime('%Y-%m')
    next_month = (today + relativedelta(months=1)).strftime('%Y-%m')

    # 今月の支出合計 (is_calcが1のもの)
    total_this = df[(df['date'].str.contains(this_month)) & (df['is_calc'] == 1) & (df['type'] == '支出')]['amount'].sum()
    
    # 来月の請求予定 (payment_monthが来月のもの)
    total_next = df[(df['payment_month'] == next_month) & (df['type'] == '支出')]['amount'].sum()
    
　　　col1, col2 = st.columns(2)  # 2つの列を作る
    col1.metric(f"📊 {this_month} の支出", f"¥{int(total_this):,}")
    col2.metric(f"📅 {next_month} の予定", f"¥{int(total_next):,}")
