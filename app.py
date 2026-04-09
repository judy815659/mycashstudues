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
        st.subheader(f"📊 {selected_month} の詳細分析")
        
        # 1. カテゴリ別の合計（これまで通り）
        if not df_actual_all.empty:
            cat_df = df_actual_all.groupby('category')['amount'].sum().sort_values(ascending=False)
            st.bar_chart(cat_df)
            
            st.divider()
            
            # 2. 【新機能】カテゴリ × 支払方法 のマトリックス表
            st.write("### 💳 カテゴリごとの支払方法の内訳")
            
            # ピボットテーブルを作成（行：カテゴリ、列：支払方法）
            pay_method_analysis = df_actual_all.pivot_table(
                index='category', 
                columns='method', 
                values='amount', 
                aggfunc='sum', 
                fill_value=0
            )
            
            # 合計列を追加して多い順に並び替え
            pay_method_analysis['合計'] = pay_method_analysis.sum(axis=1)
            pay_method_analysis = pay_method_analysis.sort_values('合計', ascending=False)
            
            # 表を見やすく表示（カンマ区切り）
            st.table(pay_method_analysis.map(lambda x: f"¥{x:,}"))
            
            # 3. 積み上げ棒グラフで視覚化
            st.write("### 📈 支払方法の構成（視覚化）")
            # 合計列を除いたデータでグラフ作成
            chart_data = pay_method_analysis.drop(columns=['合計'])
            st.bar_chart(chart_data)
            
        else:
            st.info("集計対象のデータがありません。")

with tab2:
        view_mode = st.radio("表示リスト:", [f"{selected_month} 発生分", f"{selected_month} 支払分"], horizontal=True)
        target_df = df_actual_all if "発生" in view_mode else df_pay_all
        
        # --- 並び順の修正ポイント ---
        df_display = target_df.copy()
        # 日付型に変換して確実に並び替えができるようにする
        df_display['date'] = pd.to_datetime(df_display['date'], errors='coerce')
        # 新しい日付が一番上に来るようにソート (ascending=False)
        df_display = df_display.sort_values("date", ascending=False)
        # 表示用に日付フォーマットを整える
        df_display['date'] = df_display['date'].dt.strftime('%Y-%m-%d')
        
        # 不要な内部処理用カラムを落として表示
        df_display = df_display.drop(columns=['date_dt', 'month_key', 'pay_month_clean'])
        
        edited_df = st.data_editor(
            df_display, 
            use_container_width=True, 
            num_rows="dynamic", 
            key=f"ed_{selected_month}_{view_mode}"
        )
        
        if st.button("🗑️ 変更を確定する"):
            # 保存時も全体を日付順に整えてからスプシへ飛ばす
            all_data = get_data()
            other_data = df.drop(target_df.index).drop(columns=['date_dt', 'month_key', 'pay_month_clean'])
            final_df = pd.concat([other_data, edited_df], ignore_index=True)
            
            # スプシ保存直前に日付で昇順（古い順）に並び替えておくとスプシが綺麗になります
            final_df['date'] = pd.to_datetime(final_df['date'])
            final_df = final_df.sort_values("date").reset_index(drop=True)
            
            conn.update(data=final_df)
            st.success("日付順に整理してスプレッドシートを更新しました！")
            st.rerun()
import google.generativeai as genai

# --- 5. AIアドバイザー設定 ---
st.divider()
st.header("🤖 AI家計再生アドバイザー")

# サイドバーまたは設定タブでAIへの「希望・目標」を入力できるようにします
with st.expander("📝 あなたの目標やライフスタイルをAIに教える"):
    user_vision = st.text_area(
        "AIへの指示（例：年収600万を目指している、配当生活がしたい、猫2匹との暮らしを大事にしたい、など）",
        value="年収600万円を目指しており、将来的には資産を形成して配当生活をしたい。日々のQOLも大事にしつつ、無駄な支出を鋭く指摘してほしい。",
        key="user_vision"
    )

# APIキーの入力（本来はSecrets管理がベストですが、まずは入力形式で）
api_key = st.text_input("Gemini API Keyを入力してください", type="password")

if st.button("📊 AIに今月の分析をお願いする"):
    if not api_key:
        st.warning("AIzaSyAK0aK3hh2UjjM7eoOmXal3Mt6b1lPIO1w")
    else:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # AIに渡すデータの準備
            # 今月の支出をカテゴリ別にまとめたテキストを作成
            monthly_summary = df_actual_all.groupby('category')['amount'].sum().to_string()
            
            # AIへのプロンプト
            prompt = f"""
            あなたは優秀な家計管理アドバイザーです。
            以下のユーザーの「希望」と「今月の支出データ」を分析し、目標達成のためのアドバイスを300文字程度で伝えてください。
            
            【ユーザーの希望・状況】
            {user_vision}
            
            【今月({selected_month})の支出データ】
            {monthly_summary}
            
            【アドバイスの指針】
            - 厳しいだけでなく、ユーザーのQOLや猫との生活への配慮も含めた温かい口調で。
            - 資産形成（100万円貯金）に向けた具体的な一歩を提案して。
            """
            
            with st.spinner("AIが分析中..."):
                response = model.generate_content(prompt)
                st.chat_message("assistant").write(response.text)
                
        except Exception as e:
            st.error(f"AI分析中にエラーが発生しました: {e}")
