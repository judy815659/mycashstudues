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
    amount = st.number_input("金額 (円)", min_value=0, step=1, value=st.session_state['ocr_amount'])
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
                "amount": int(amount),
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
    # --- 型変換の徹底（計算エラー防止） ---
    df = df.copy()
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0).astype(int)
    
    def cleanup_bool(x):
        if str(x).upper() in ["TRUE", "1", "1.0", "YES"]: return 1
        return 0
    df['is_calc_clean'] = df['is_calc'].apply(cleanup_bool)
    
    df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_key'] = df['date_dt'].dt.strftime('%Y-%m')
    df['pay_month_clean'] = df['payment_month'].astype(str).str.replace('/', '-').str.strip()

    # 月の選択
    available_months = sorted(df['month_key'].dropna().unique(), reverse=True)
    if not available_months:
        available_months = [datetime.now().strftime('%Y-%m')]
    selected_month = st.selectbox("表示する月を選択してください", available_months)

    # --- 集計 ---
    df_actual = df[(df['month_key'] == selected_month) & (df['type'].str.contains('支出')) & (df['is_calc_clean'] == 1)]
    total_actual = int(df_actual['amount'].sum())

    df_pay = df[(df['pay_month_clean'] == selected_month) & (df['type'].str.contains('支出'))]
    total_pay = int(df_pay['amount'].sum())

    # --- 表示 ---
    col1, col2 = st.columns(2)
    col1.metric(f"📊 {selected_month} の実支出", f"¥{total_actual:,}")
    col2.metric(f"📅 {selected_month} の引落予定", f"¥{total_pay:,}")

    st.divider()

    # --- 📈 分析 & 📝 履歴のタブ分け ---
    tab1, tab2, tab3 = st.tabs(["🍕 カテゴリ内訳", "📈 支出推移", "📝 履歴の編集・削除"])

    with tab1:
        if not df_actual.empty:
            category_df = df_actual.groupby('category')['amount'].sum().sort_values(ascending=False)
            st.bar_chart(category_df)
            st.table(category_df.map(lambda x: f"¥{x:,}"))
        else:
            st.info("この月の支出データはありません。")

    with tab2:
        monthly_trend = df[df['type'].str.contains('支出')].groupby('month_key')['amount'].sum().reset_index()
        st.line_chart(data=monthly_trend, x='month_key', y='amount')

    with tab3:
        st.subheader(f"{selected_month} の詳細明細")
        # 選択した月のデータだけを表示用に整理
        df_history = df[df['month_key'] == selected_month].copy()
        df_history['date'] = df_history['date_dt'].dt.strftime('%Y-%m-%d')
        # 不要なデバッグ用列を削除して表示
        df_display = df_history.drop(columns=['date_dt', 'month_key', 'is_calc_clean', 'pay_month_clean']).sort_values("date", ascending=False)
        
        # 編集エディタ
        edited_df = st.data_editor(
            df_display, 
            use_container_width=True, 
            num_rows="dynamic",
            key=f"editor_{selected_month}"
        )
        
        if st.button("🗑️ 変更をスプシに反映する"):
            # 他の月のデータと合体させて保存
            other_months = df[df['month_key'] != selected_month].drop(columns=['date_dt', 'month_key', 'is_calc_clean', 'pay_month_clean'])
            final_df = pd.concat([other_months, edited_df], ignore_index=True)
            conn.update(data=final_df)
            st.success("スプレッドシートを更新しました！")
            st.rerun()

    st.link_button("📈 スプレッドシートを直接開く", "https://docs.google.com/spreadsheets/d/1debBotyTDwqUAmcEox0fdJIuvyv7Cko6I3NlvCTNVhY/edit")
else:
    st.info("データがありません。サイドバーから入力してください。")
