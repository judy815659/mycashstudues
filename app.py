import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

# --- 1. スプレッドシート接続設定 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    # スプシから全データを読み込む（キャッシュを無効化して常に最新を取得）
    return conn.read(ttl=0)

# --- 2. 画面設定 ---
st.set_page_config(page_title="My家計簿アプリ", layout="wide")
st.title("💰 スプシ連携・家計簿アプリ")

# --- 3. サイドバー入力 ---
with st.sidebar:
    st.header("新規入力")
    
    # セッション状態の初期化
    if 'ocr_amount' not in st.session_state: st.session_state['ocr_amount'] = 0
    if 'ocr_date' not in st.session_state: st.session_state['ocr_date'] = datetime.now()
    if 'ocr_memo' not in st.session_state: st.session_state['ocr_memo'] = ""

    # 入力フォーム
    target_date = st.date_input("日付", value=st.session_state['ocr_date'])
    category = st.selectbox("カテゴリ", ["食費", "外食", "日用品", "娯楽", "固定費", "分割払", "給与", "その他"])
    
    t_type_index = 1 if category == "給与" else 0
    t_type = st.radio("収支種別", ["支出", "収入"], index=t_type_index)
    
    amount = st.number_input("金額 (円)", min_value=0, step=100, value=st.session_state['ocr_amount'])
    method = st.selectbox("支払方法", ["現金", "クレジットカード", "Paydy(後払い)", "d払い", "デビットカード"])
    memo = st.text_area("備考（メモ）", value=st.session_state['ocr_memo'], placeholder="Amazonの注文内容など")
    is_calc = st.checkbox("今月の収支集計に含める", value=True)

    # --- コピペ抽出エリア ---
    st.markdown("---")
    st.subheader("📝 テキストから抽出")
    pasted_text = st.text_area("ここにコピー内容をペースト", height=80)

    if pasted_text:
        # 数字と日付の抽出
        found_amounts = re.findall(r'\b\d{3,6}\b', pasted_text.replace(',', ''))
        date_patterns = [r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', r'(\d{1,2}月\d{1,2}日)']
        found_dates = []
        for p in date_patterns: found_dates.extend(re.findall(p, pasted_text))

        if found_amounts or found_dates or pasted_text:
            st.caption("クリックで反映：")
            if found_amounts:
                unique_amts = sorted(list(set(found_amounts)), key=int, reverse=True)[:3]
                cols = st.columns(len(unique_amts))
                for i, num in enumerate(unique_amts):
                    if cols[i].button(f"¥{num}"):
                        st.session_state['ocr_amount'] = int(num); st.rerun()
            if found_dates:
                for d_str in list(set(found_dates))[:2]:
                    if st.button(f"📅 {d_str}"):
                        clean_d = d_str.replace('年', '-').replace('月', '-').replace('日', '')
                        if '-' not in clean_d[:2]: clean_d = f"{datetime.now().year}-{clean_d}"
                        st.session_state['ocr_date'] = pd.to_datetime(clean_d); st.rerun()
            if st.button("📝 テキストを備考にコピー"):
                st.session_state['ocr_memo'] = pasted_text.replace('\n', ' ')[:100]; st.rerun()

    if st.button("💾 スプシへ保存"):
        try:
            # 現在のデータを取得。もし空っぽなら新しいDFを作る
            try:
                df_current = get_data()
            except:
                df_current = pd.DataFrame(columns=["date", "category", "amount", "method", "type", "payment_month", "memo", "is_calc"])
            
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
            
            # 既存データと結合（空の場合はnew_rowのみ）
            if df_current is not None and not df_current.empty:
                updated_df = pd.concat([df_current, new_row], ignore_index=True)
            else:
                updated_df = new_row
            
            # スプシを上書き更新
            conn.update(data=updated_df)
            
            st.success("スプレッドシートに保存しました！")
            st.session_state['ocr_amount'] = 0
            st.rerun()
            
        except Exception as e:
            st.error(f"保存に失敗しました。共有設定が『編集者』になっているか確認してください。エラー詳細: {e}")

# --- 4. メイン表示 ---
df = get_data()

if df is not None and not df.empty:
    this_month = datetime.now().strftime('%Y-%m')
    df['date'] = df['date'].astype(str)
    
    # 集計ロジック
    df_this_month = df[df['date'].str.contains(this_month)]
    df_calc = df_this_month[df_this_month['is_calc'] == 1]
    total_expense = pd.to_numeric(df_calc[df_calc['type'] == '支出']['amount'], errors='coerce').fillna(0).sum()
    
    st.header(f"📊 {this_month} の支出合計")
    st.metric("総支出", f"¥{int(total_expense):,}")
    
    st.divider()
    st.subheader("履歴の管理（削除もこちら）")
    
    # st.data_editor を使うことで、行の選択が可能になります
    # 削除しやすいようにインデックス（行番号）を表示します
    edited_df = st.data_editor(
        df.sort_values("date", ascending=False),
        use_container_width=True,
        num_rows="dynamic",  # 行の選択・削除を可能にする設定
        key="data_editor"
    )

    # 削除の実行ボタン
    if st.button("🗑️ 選択した行をスプシから削除する"):
        # 元のdfと表示中のedited_dfを比較して、消されたデータを確認
        # インデックスが変わらないように現在の表示内容でスプシを丸ごと上書きします
        try:
            conn.update(data=edited_df)
            st.success("スプレッドシートを更新（削除完了）しました！")
            st.rerun()
        except Exception as e:
            st.error(f"削除に失敗しました: {e}")
            
    st.caption("※左端のチェックボックスで選択して『Deleteキー』または『ゴミ箱アイコン』で消してから、上のボタンを押してください。")

else:
    st.info("スプレッドシートにデータがありません。")
