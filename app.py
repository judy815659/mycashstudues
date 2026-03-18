import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

# --- 1. スプレッドシート接続設定 ---
# Streamlit CloudのSecretsに設定したURLを使って接続します
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    # スプシから全データを読み込む
    return conn.read(ttl=0) # ttl=0で常に最新を取得

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
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "固定費", "分割払", "給与", "その他"])
    t_type_index = 1 if category == "給与" else 0
    t_type = st.radio("収支種別", ["支出", "収入"], index=t_type_index)
    amount = st.number_input("金額 (円)", min_value=0, step=100, value=st.session_state['ocr_amount'])
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "Paydy(後払い)", "d払い", "デビットカード"])
    memo = st.text_area("備考（メモ）", value=st.session_state['ocr_memo'])
    is_calc = st.checkbox("今月の収支集計に含める", value=True)

    # (中略：OCR/コピペ抽出ロジックは前回と同じなので維持)
    # ... [ここには前回のOCR抽出ロジックが入ります] ...

    if st.button("💾 スプシへ保存"):
        # 現在のデータを取得
        df = get_data()
        # 新しい行を作成
        new_row = pd.DataFrame([{
            "date": target_date.strftime('%Y-%m-%d'),
            "category": category,
            "amount": amount,
            "method": method,
            "type": t_type,
            "payment_month": target_date.strftime('%Y-%m'),
            "memo": memo,
            "is_calc": 1 if is_calc else 0
        }])
        # 結合してスプシを更新
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(data=updated_df)
        
        st.session_state['ocr_amount'] = 0
        st.success("スプレッドシートに保存しました！")
        st.rerun()

# --- 4. メイン表示 ---
df = get_data()

if not df.empty:
    this_month = datetime.now().strftime('%Y-%m')
    # 日付列を文字列として扱い、今月のデータを抽出
    df['date'] = df['date'].astype(str)
    df_this_month = df[df['date'].str.contains(this_month)]
    
    # 集計
    df_calc = df_this_month[df_this_month['is_calc'] == 1]
    total_expense = pd.to_numeric(df_calc[df_calc['type'] == '支出']['amount']).sum()
    
    st.header(f"📊 {this_month} の支出合計")
    st.metric("総支出", f"¥{int(total_expense):,}")
    
    st.subheader("履歴（スプレッドシート同期中）")
    # 削除機能などはスプシ側で直接行を消すのが一番安全ですが、
    # 簡易的に表示するだけならこちら
    st.dataframe(df.sort_values("date", ascending=False), use_container_width=True)
else:
    st.info("スプレッドシートにデータがありません。1行目（ヘッダー）が正しく入力されているか確認してください。")
