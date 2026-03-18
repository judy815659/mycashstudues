import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

# --- 1. データベース設定（memo列を追加） ---
def init_db():
    conn = sqlite3.connect('kakeibo_v7.db')
    cursor = conn.cursor()
    # 既存のテーブルにmemo列がない場合も考慮して、常にカラムを確認・作成
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            category TEXT,
            amount INTEGER,
            method TEXT,
            type TEXT,
            payment_month TEXT,
            memo TEXT
        )
    ''')
    conn.commit()
    return conn

# --- 2. 画面設定 ---
st.set_page_config(page_title="My家計簿アプリ", layout="centered")
st.title("💰 Simple家計簿 & 支払い管理")

# --- 3. サイドバー入力 ---
with st.sidebar:
    st.header("新規入力")
    
    if 'ocr_amount' not in st.session_state: st.session_state['ocr_amount'] = 0
    if 'ocr_date' not in st.session_state: st.session_state['ocr_date'] = datetime.now()
    if 'ocr_memo' not in st.session_state: st.session_state['ocr_memo'] = ""

    # 入力フォーム
    target_date = st.date_input("日付", value=st.session_state['ocr_date'])
    
    category_list = ["食費", "外食", "日用品", "娯楽", "固定費", "分割払", "給与", "その他"]
    category = st.selectbox("カテゴリ", category_list)
    
    t_type_index = 1 if category == "給与" else 0
    t_type = st.radio("収支種別", ["支出", "収入"], index=t_type_index)
    
    amount = st.number_input("金額 (円)", min_value=0, step=100, value=st.session_state['ocr_amount'])
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "d払い", "デビットカード", "paydy"])
    
    # 【新機能】備考欄
    memo = st.text_area("備考（メモ）", value=st.session_state['ocr_memo'], placeholder="店名や買ったものなど")

    # --- コピペ抽出エリア ---
    st.markdown("---")
    st.subheader("📝 レシートから自動抽出")
    pasted_text = st.text_area("ここにコピー内容をペースト", height=80)

    if pasted_text:
        # 数字と日付の抽出
        found_amounts = re.findall(r'\b\d{3,6}\b', pasted_text.replace(',', ''))
        date_patterns = [r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', r'(\d{1,2}月\d{1,2}日)']
        found_dates = []
        for p in date_patterns:
            found_dates.extend(re.findall(p, pasted_text))

        if found_amounts or found_dates or pasted_text:
            st.caption("クリックで反映：")
            
            # 金額ボタン
            if found_amounts:
                unique_amts = sorted(list(set(found_amounts)), key=int, reverse=True)[:3]
                cols = st.columns(len(unique_amts))
                for i, num in enumerate(unique_amts):
                    if cols[i].button(f"¥{num}"):
                        st.session_state['ocr_amount'] = int(num)
                        st.rerun()

            # 日付ボタン
            if found_dates:
                for d_str in list(set(found_dates))[:2]:
                    if st.button(f"📅 {d_str} を反映"):
                        try:
                            clean_d = d_str.replace('年', '-').replace('月', '-').replace('日', '')
                            if '-' not in clean_d[:2]: clean_d = f"{datetime.now().year}-{clean_d}"
                            st.session_state['ocr_date'] = pd.to_datetime(clean_d)
                            st.rerun()
                        except: st.error("日付形式エラー")

            # 【新機能】テキスト全体を備考に反映させるボタン
            if st.button("📝 テキストを備考にコピー"):
                # 改行をスペースに置換して、先頭50文字くらいをセット
                st.session_state['ocr_memo'] = pasted_text.replace('\n', ' ')[:100]
                st.rerun()

    # --- 保存ボタン ---
    st.markdown("---")
    if st.button("💾 データを保存"):
        conn = init_db()
        cur = conn.cursor()
        save_date_str = target_date.strftime('%Y-%m-%d')
        
        cur.execute("""
            INSERT INTO records (date, category, amount, method, type, payment_month, memo) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (save_date_str, category, amount, method, t_type, save_date_str[:7], memo))
        
        conn.commit()
        # リセット
        st.session_state['ocr_amount'] = 0
        st.session_state['ocr_date'] = datetime.now()
        st.session_state['ocr_memo'] = ""
        st.success(f"保存完了！")
        st.rerun()

# --- 4. メイン表示 ---
conn = init_db()
# 削除しやすいように ID も取得します
df = pd.read_sql_query("SELECT id, date, category, amount, type, memo, method FROM records ORDER BY date DESC", conn)

if not df.empty:
    this_month = datetime.now().strftime('%Y-%m')
    df_this_month = df[df['date'].str.contains(this_month)]
    total_expense = df_this_month[df_this_month['type'] == '支出']['amount'].sum()
    
    st.header(f"📊 {this_month} の支出合計")
    st.metric("総支出", f"¥{total_expense:,}")
    
    st.divider()
    st.subheader("履歴の管理")
    
    # 【新機能】データ選択削除
    # st.data_editor を使うと、左側にチェックボックスが出現します
    edited_df = st.data_editor(
        df,
        column_config={
            "id": None,  # IDは見せなくて良いので非表示
        },
        disabled=["date", "category", "amount", "type", "memo", "method"], # 中身の編集は不可にする
        use_container_width=True,
        key="data_editor",
        num_rows="dynamic" # 行の選択を可能に
    )

    # 選択された行を特定して削除するボタン
    # data_editorのステータスから、削除（選択）された行を取得
    if st.button("🗑️ 選択した行を削除する"):
        # 実際には「消された行」以外のデータが edited_df に残るので、
        # データベースを現在の表示内容で上書きするか、差分で消す処理をします
        
        # もっとも確実な「削除されたID」を特定する方法
        current_ids = edited_df["id"].tolist()
        all_ids = df["id"].tolist()
        delete_ids = list(set(all_ids) - set(current_ids))

        if delete_ids:
            cursor = conn.cursor()
            for d_id in delete_ids:
                cursor.execute("DELETE FROM records WHERE id = ?", (d_id,))
            conn.commit()
            st.success(f"{len(delete_ids)} 件のデータを削除しました。")
            st.rerun()
        else:
            st.info("削除したい行を左側のチェックボックスで選択して、ゴミ箱アイコン（またはDeleteキー）で消してからこのボタンを押してください。")
else:
    st.info("データがありません。")
