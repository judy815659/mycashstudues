import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re
import google.generativeai as genai  # ←冒頭にまとめました

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
    
    if 'ocr_amount' not in st.session_state: st.session_state['ocr_amount'] = 0
    if 'ocr_date' not in st.session_state: st.session_state['ocr_date'] = datetime.now()
    if 'ocr_memo' not in st.session_state: st.session_state['ocr_memo'] = ""

    target_date = st.date_input("日付", value=st.session_state['ocr_date'])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "医療費", "交通費", "固定費", "分割払", "給与", "その他"])
    t_type = st.radio("収支種別", ["支出", "収入"], index=1 if category == "給与" else 0)
    amount = st.number_input("金額 (円)", min_value=0, step=1, value=st.session_state['ocr_amount'])
    
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "Paydy(後払い)", "d払い", "デビットカード"])
    
    deferred_methods = ["クレジットカード", "Paydy(後払い)", "d払い"]
    
    if method in deferred_methods:
        auto_pay_month = (target_date + relativedelta(months=1)).strftime('%Y-%m')
        auto_is_calc = False  
    else:
        auto_pay_month = target_date.strftime('%Y-%m')
        auto_is_calc = True

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
            st.success(f"保存完了！")
            st.session_state['ocr_amount'] = 0
            st.rerun()
        except Exception as e:
            st.error(f"保存失敗: {e}")

# --- 4. メイン表示 ---
df = get_data()

if df is not None and not df.empty:
    df = df.copy()
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0).astype(int)
    df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_key'] = df['date_dt'].dt.strftime('%Y-%m')
    df['pay_month_clean'] = df['payment_month'].astype(str).str.replace('/', '-').str.strip()

    available_months = sorted(df['month_key'].dropna().unique(), reverse=True)
    selected_month = st.selectbox("表示する月を選択してください", available_months)

    df_actual_all = df[(df['month_key'] == selected_month) & (df['type'].str.contains('支出'))]
    total_actual = int(df_actual_all['amount'].sum())

    df_pay_all = df[(df['pay_month_clean'] == selected_month) & (df['type'].str.contains('支出'))]
    total_pay = int(df_pay_all['amount'].sum())

# --- 支出の集計 ---
    df_actual_all = df[(df['month_key'] == selected_month) & (df['type'].str.contains('支出'))]
    total_actual = int(df_actual_all['amount'].sum())

    # --- 収入の集計（新しく追加） ---
    df_income_all = df[(df['month_key'] == selected_month) & (df['type'].str.contains('収入'))]
    total_income = int(df_income_all['amount'].sum())

    # --- 収支（貯金）の計算 ---
    balance = total_income - total_actual

    # 表示（3カラムに変更）
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(f"💰 {selected_month} の総収入", f"¥{total_income:,}")
    with col2:
        st.metric(f"🛒 {selected_month} の支出合計", f"¥{total_actual:,}")
    with col3:
        # 収支がプラスなら緑、マイナスなら赤で表示
        st.metric(f"🌱 今月の収支残高", f"¥{balance:,}", delta=f"{balance:,}")

    st.divider()

    # --- タブの設定（AIアドバイザーを独立させました） ---
    tab1, tab2, tab3, tab4 = st.tabs(["📊 カテゴリ内訳", "📈 収入・収支分析", "📝 履歴を確認・修正", "🤖 AIアドバイザー"])

    with tab1:
        # （これまでの支出グラフコードをそのまま記載）
        st.subheader(f"📊 {selected_month} の支出分析")
        if not df_actual_all.empty:
            cat_df = df_actual_all.groupby('category')['amount'].sum().sort_values(ascending=False)
            st.bar_chart(cat_df)
        else:
            st.info("支出データがありません。")

    with tab2:
        st.subheader("📈 収支のバランス")
        if total_income > 0 or total_actual > 0:
            # 収入と支出の比較グラフ
            balance_df = pd.DataFrame({
                "種別": ["収入", "支出"],
                "金額": [total_income, total_actual]
            })
            st.bar_chart(data=balance_df, x="種別", y="金額")
            
            # 収入の内訳（給与以外がある場合など）
            if not df_income_all.empty:
                st.write("### 💵 収入の内訳")
                income_cat = df_income_all.groupby('category')['amount'].sum()
                st.table(income_cat.map(lambda x: f"¥{x:,}"))
        else:
            st.info("収入・支出のデータが不足しています。")

    # （以下、tab3: 履歴、tab4: AIアドバイザーと続きます）

    # --- 5. AIアドバイザー・セクション（tab3） ---
    with tab3:
        st.header("🤖 AI家計再生アドバイザー")
        
        # SecretsからAPIキーを取得
        if "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            
            with st.expander("📝 あなたの目標をカスタマイズ", expanded=True):
                user_vision = st.text_area(
                    "AIに考慮してほしいこと",
                    value="年収600万円を目指しており、将来的には資産を形成して配当生活をしたい。猫2匹との暮らしを大事にしつつ、無駄な支出を鋭く指摘してほしい。"
                )

            if st.button("📊 AIに今月の分析をお願いする"):
                if not df_actual_all.empty:
                    try:
                        # 'models/' を付けるか、最新の 2.0-flash を試してみてください
                        model = genai.GenerativeModel('models/gemini-1.5-flash')
                        monthly_summary = df_actual_all.groupby('category')['amount'].sum().to_string()
                        
                        prompt = f"""
                        あなたは優秀な家計管理アドバイザーです。
                        ユーザーの目標: {user_vision}
                        今月の支出データ: {monthly_summary}
                        
                        上記に基づき、目標達成（年収600万・配当生活）に向けた具体的なアドバイスを、
                        猫2匹との生活への配慮も込めて、200〜300文字程度で温かい口調で伝えてください。
                        """
                        
                        with st.spinner("AIが分析中..."):
                            response = model.generate_content(prompt)
                            st.info(response.text)
                    except Exception as e:
                        st.error(f"AI分析中にエラーが発生しました: {e}")
                else:
                    st.warning("分析するための今月のデータがありません。")
        else:
            st.error("Streamlit CloudのSecretsに 'GEMINI_API_KEY' が設定されていません。")
