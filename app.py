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
st.title("💰 スプシ連携・自動仕分け家計簿")

# --- 3. サイドバー入力 ---
with st.sidebar:
    st.header("新規入力")
    
    # セッション状態の初期化
    if 'ocr_amount' not in st.session_state: st.session_state['ocr_amount'] = 0
    if 'ocr_date' not in st.session_state: st.session_state['ocr_date'] = datetime.now()
    if 'ocr_memo' not in st.session_state: st.session_state['ocr_memo'] = ""

    target_date = st.date_input("日付", value=st.session_state['ocr_date'])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "医療費", "交通費", "固定費", "分割払", "給与", "その他"])
    t_type = st.radio("収支種別", ["支出", "収入"], index=1 if category == "給与" else 0)
    amount = st.number_input("金額 (円)", min_value=0, step=1, value=st.session_state['ocr_amount'])
    
    # --- 自動仕分けロジックの核 ---
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "Paydy(後払い)", "d払い", "デビットカード"])
    
    # 翌月払いになる方法をリスト化
    deferred_methods = ["クレジットカード", "Paydy(後払い)", "d払い"]
    
    if method in deferred_methods:
        # 自動で「翌月払い」をセット
        auto_pay_month = (target_date + relativedelta(months=1)).strftime('%Y-%m')
        auto_is_calc = False  # 今月の「現金管理」からは外す
    else:
        # 「その場で支払い」をセット
        auto_pay_month = target_date.strftime('%Y-%m')
        auto_is_calc = True

    # 自動設定されるが、手動での微調整も可能
    pay_month = st.text_input("支払い月 (YYYY-MM)", value=auto_pay_month)
    is_calc = st.checkbox("今月の収支集計に含める", value=auto_is_calc)
    
    memo = st.text_area("備考（メモ）", value=st.session_state['ocr_memo'])

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
            st.success(f"保存完了！ ({method}により自動仕分け)")
            st.session_state['ocr_amount'] = 0
            st.rerun()
        except Exception as e:
            st.error(f"保存失敗: {e}")

# --- 4. メイン表示 ---
df = get_data()

if df is not None and not df.empty:
    # データクレンジング
    df = df.copy()
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0).astype(int)
    df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_key'] = df['date_dt'].dt.strftime('%Y-%m')
    df['pay_month_clean'] = df['payment_month'].astype(str).str.replace('/', '-').str.strip()

    # 月選択
    available_months = sorted(df['month_key'].dropna().unique(), reverse=True)
    selected_month = st.selectbox("表示する月を選択してください", available_months)

    # 集計
    df_actual_all = df[(df['month_key'] == selected_month) & (df['type'].str.contains('支出'))]
    total_actual = int(df_actual_all['amount'].sum())

    df_pay_all = df[(df['pay_month_clean'] == selected_month) & (df['type'].str.contains('支出'))]
    total_pay = int(df_pay_all['amount'].sum())

    # 表示
    col1, col2 = st.columns(2)
    with col1:
        st.metric(f"🛒 {selected_month} に買った合計", f"¥{total_actual:,}")
        st.caption("※日付がこの月の買い物（贅沢した総額）")
    with col2:
        st.metric(f"💸 {selected_month} の引落合計", f"¥{total_pay:,}")
        st.caption("※支払い月がこの月の引落額（口座残高が必要な額）")

    st.divider()

    # タブ
    tab1, tab2 = st.tabs(["📊 カテゴリ内訳", "📝 履歴を確認・修正"])

    with tab1:
        if not df_actual_all.empty:
            cat_df = df_actual_all.groupby('category')['amount'].sum().sort_values(ascending=False)
            st.bar_chart(cat_df)
            st.table(cat_df.map(lambda x: f"¥{x:,}"))

    with tab2:
        view_mode = st.radio("表示リスト:", [f"{selected_month} 発生分", f"{selected_month} 支払分"], horizontal=True)
        target_df = df_actual_all if "発生" in view_mode else df_pay_all
        
        df_display = target_df.copy()
        df_display['date'] = df_display['date_dt'].dt.strftime('%Y-%m-%d')
        df_display = df_display.drop(columns=['date_dt', 'month_key', 'pay_month_clean']).sort_values("date", ascending=False)
        
        edited_df = st.data_editor(df_display, use_container_width=True, num_rows="dynamic", key=f"ed_{selected_month}_{view_mode}")
        
        if st.button("🗑️ 変更を確定する"):
            all_data = get_data()
            # 既存データから対象月の分を除いて合体
            other_data = df.drop(target_df.index).drop(columns=['date_dt', 'month_key', 'pay_month_clean'])
            final_df = pd.concat([other_data, edited_df], ignore_index=True)
            conn.update(data=final_df)
            st.success("スプレッドシートを更新しました")
            st.rerun()

    st.link_button("📈 スプレッドシートを直接開く", "https://docs.google.com/spreadsheets/d/1debBotyTDwqUAmcEox0fdJIuvyv7Cko6I3NlvCTNVhY/edit")
else:
    st.info("データがありません。")
