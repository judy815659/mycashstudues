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
    # データ型の整理
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_key'] = df['date_dt'].dt.strftime('%Y-%m') # 発生ベースの月
    df['payment_month'] = df['payment_month'].astype(str).str.replace('/', '-') # 支払いベースの月

    # --- 📅 表示する月の選択 ---
    # スプシにある全月をリスト化して選択可能にする
    available_months = sorted(df['month_key'].dropna().unique(), reverse=True)
    selected_month = st.selectbox("表示する月を選択してください", available_months)

    # 選択された月のデータを抽出
    # 1. その月の「支出」合計 (is_calc=1のもの)
    df_selected_actual = df[(df['month_key'] == selected_month) & (df['is_calc'] == 1) & (df['type'] == '支出')]
    total_actual = df_selected_actual['amount'].sum()

    # 2. その月に「支払う予定（クレカ等）」の合計 (payment_monthが一致するもの)
    df_selected_pay = df[(df['payment_month'] == selected_month) & (df['type'] == '支出')]
    total_pay = df_selected_pay['amount'].sum()

    # メトリック表示
    col1, col2 = st.columns(2)
    col1.metric(f"📊 {selected_month} の実支出", f"¥{int(total_actual):,}")
    col2.metric(f"📅 {selected_month} の引落し・支払予定", f"¥{int(total_pay):,}")

    st.divider()

    # --- 📈 分析セクション ---
    tab1, tab2 = st.tabs(["🍕 カテゴリ内訳", "📈 支出推移"])

    with tab1:
        st.subheader(f"{selected_month} のカテゴリ別内訳")
        if not df_selected_actual.empty:
            pie_data = df_selected_actual.groupby('category')['amount'].sum().sort_values(ascending=False)
            st.bar_chart(pie_data)
            st.table(pie_data)
        else:
            st.info("この月のデータはありません。")

    with tab2:
        st.subheader("月別の支出推移")
        monthly_trend = df[df['type'] == '支出'].groupby('month_key')['amount'].sum().reset_index()
        st.line_chart(data=monthly_trend, x='month_key', y='amount')

    st.divider()
    
    # --- 履歴一覧 ---
    st.subheader(f"📝 {selected_month} の履歴")
    # 選択した月だけの履歴を表示
    df_history = df[df['month_key'] == selected_month].sort_values("date", ascending=False)
    # 表示用に不要な列を隠す
    df_history = df_history.drop(columns=['date_dt', 'month_key'])
    
    edited_df = st.data_editor(df_history, use_container_width=True, num_rows="dynamic")
    
    if st.button("🗑️ この月の変更を反映する"):
        # 注意：このボタンは表示されている月以外のデータに影響を与えないよう、
        # 既存の全データとマージして更新する必要があります
        other_months_df = df[df['month_key'] != selected_month].drop(columns=['date_dt', 'month_key'])
        final_df = pd.concat([other_months_df, edited_df], ignore_index=True)
        conn.update(data=final_df)
        st.success("更新しました！")
        st.rerun()
else:
    st.info("データがありません。")
