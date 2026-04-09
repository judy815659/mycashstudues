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

# (前半のインポートや入力部分は変更なしのため、メイン表示部分を強化します)

# --- 4. メイン表示 ---
df = get_data()

if df is not None and not df.empty:
    df = df.copy()
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0).astype(int)
    df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_key'] = df['date_dt'].dt.strftime('%Y-%m')
    df['pay_month_clean'] = df['payment_month'].astype(str).str.replace('/', '-').str.strip()

    # 月の選択
    available_months = sorted(df['month_key'].dropna().unique(), reverse=True)
    selected_month = st.selectbox("表示する月を選択してください", available_months)

    # --- 厳密な集計ロジック ---
    # A. 【3月に買ったもの全部】 (is_calcに関わらず、その月に発生した支出)
    df_actual_all = df[(df['month_key'] == selected_month) & (df['type'].str.contains('支出'))]
    total_actual = int(df_actual_all['amount'].sum())

    # B. 【3月に支払ったもの全部】 (payment_monthが3月の支出)
    df_pay_all = df[(df['pay_month_clean'] == selected_month) & (df['type'].str.contains('支出'))]
    total_pay = int(df_pay_all['amount'].sum())

    # --- 表示 ---
    col1, col2 = st.columns(2)
    with col1:
        st.metric(f"🛒 {selected_month} に買った合計", f"¥{total_actual:,}")
        st.caption("※日付がこの月の支出すべて（発生ベース）")
    with col2:
        st.metric(f"💸 {selected_month} の引落合計", f"¥{total_pay:,}")
        st.caption("※支払い月がこの月の支出すべて（キャッシュレス等）")

    st.divider()

    # --- 📈 分析 & 📝 履歴 ---
    tab1, tab2 = st.tabs(["📊 カテゴリ内訳", "📝 履歴を確認・修正"])

    with tab1:
        st.subheader(f"{selected_month} のカテゴリ内訳 (発生ベース)")
        if not df_actual_all.empty:
            category_df = df_actual_all.groupby('category')['amount'].sum().sort_values(ascending=False)
            st.bar_chart(category_df)
            st.table(category_df.map(lambda x: f"¥{x:,}"))

    with tab2:
        # 見たいリストの切り替え
        view_mode = st.radio(
            "表示するリストを選択:",
            [f"{selected_month} に「買った」ものリスト", f"{selected_month} に「支払った」ものリスト"],
            horizontal=True
        )

        if "「買った」" in view_mode:
            target_df = df_actual_all.copy()
        else:
            target_df = df_pay_all.copy()

        target_df['date'] = target_df['date_dt'].dt.strftime('%Y-%m-%d')
        df_display = target_df.drop(columns=['date_dt', 'month_key', 'pay_month_clean']).sort_values("date", ascending=False)
        
        # 編集エディタ
        edited_df = st.data_editor(
            df_display, 
            use_container_width=True, 
            num_rows="dynamic",
            key=f"editor_{selected_month}_{view_mode}"
        )
        
        if st.button("🗑️ 変更をスプレッドシートに反映する"):
            # 編集されたデータ以外を抽出して合体（更新ロジック）
            # ※この簡易更新では、全体を読み直して該当月以外とマージします
            all_data = get_data()
            # 編集対象外のデータを特定して残し、新しいデータを追加する形
            st.info("スプレッドシートを更新中...")
            conn.update(data=pd.concat([df.drop(target_df.index), edited_df], ignore_index=True))
            st.success("更新しました！")
            st.rerun()

    st.link_button("📈 スプレッドシートを直接開いて確認", "https://docs.google.com/spreadsheets/d/1debBotyTDwqUAmcEox0fdJIuvyv7Cko6I3NlvCTNVhY/edit")
