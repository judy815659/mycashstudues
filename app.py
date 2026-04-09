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
st.write(f"デバッグ情報：現在スプシから {len(df)} 件のデータを読み込んでいます")

if df is not None and not df.empty:
    # データの型を強制的に変換（計算エラー防止）
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month'] = df['date'].dt.strftime('%Y-%m')  # グラフ用に「月」列を作成

    # 今月の取得
    today = datetime.now()
    this_month_str = today.strftime('%Y-%m')
    next_month_str = (today + relativedelta(months=1)).strftime('%Y-%m')

    # メトリック表示（今月と来月）
    col1, col2 = st.columns(2)
    total_this = df[(df['month'] == this_month_str) & (df['is_calc'] == 1) & (df['type'] == '支出')]['amount'].sum()
    total_next = df[(df['payment_month'].astype(str).str.contains(next_month_str)) & (df['type'] == '支出')]['amount'].sum()
    
    col1.metric(f"📊 {this_month_str} の総支出", f"¥{int(total_this):,}")
    col2.metric(f"📅 {next_month_str} の請求予定", f"¥{int(total_next):,}")

    st.divider()

    # --- 📈 分析セクション ---
    st.header("🔍 家計の振り返り・分析")
    
    tab1, tab2 = st.tabs(["📈 月別の推移", "🍕 カテゴリ内訳"])

    with tab1:
        st.subheader("月別支出の推移")
        # 月ごとに支出を合計（収入を除外）
        monthly_df = df[df['type'] == '支出'].groupby('month')['amount'].sum().reset_index()
        # 棒グラフを表示
        st.bar_chart(data=monthly_df, x='month', y='amount', color="#ff4b4b")

    with tab2:
        st.subheader(f"{this_month_str} のカテゴリ別内訳")
        # 今月の支出内訳を抽出
        category_df = df[(df['month'] == this_month_str) & (df['type'] == '支出')]
        if not category_df.empty:
            pie_data = category_df.groupby('category')['amount'].sum()
            st.write("カテゴリごとの合計額（多い順）")
            st.table(pie_data.sort_values(ascending=False))
            # 円グラフは標準機能だと少し弱いので、簡易的に棒グラフでも内訳を表示
            st.bar_chart(pie_data)
        else:
            st.info("今月の支出データがまだありません。")

    st.divider()
    # --- 履歴一覧（削除・修正） ---
    st.subheader("📝 履歴一覧")
    # 日付順に並び替えて表示（型を文字列に戻して表示）
    df_display = df.copy()
    df_display['date'] = df_display['date'].dt.strftime('%Y-%m-%d')
    edited_df = st.data_editor(df_display.sort_values("date", ascending=False).drop(columns=['month']), use_container_width=True, num_rows="dynamic")
    
    if st.button("🗑️ 変更を確定する"):
        conn.update(data=edited_df)
        st.success("スプシを更新しました！")
        st.rerun()

else:
    st.info("データがまだありません。")
