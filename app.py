import streamlit as st
import pandas as pd
import requests
from gtts import gTTS
import tempfile
import os
import uuid
from io import StringIO, BytesIO
import time

# 🎯 구글 시트 주소 설정 (여기만 수정하면 됩니다!)
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTZltgfm_yfhVNBHaK8Aj1oQArXZhn8woXNn9hM_NIjryHQeVgkt3KP3xEx6h-IlHVFFlbxgQS2l5A5/pub?output=csv"

# 페이지 설정
st.set_page_config(
    page_title="🎓 영어 단어장",
    page_icon="📚",
    layout="wide"
)

# 세션 상태 초기화
if 'vocab_data' not in st.session_state:
    st.session_state.vocab_data = None
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False

def convert_sheet_url(original_url):
    """구글 시트 링크를 CSV 형식으로 변환"""
    url = original_url.strip()
    if 'output=csv' in url:
        return url
    if 'pubhtml' in url:
        return url.replace('pubhtml', 'pub?output=csv')
    if '/edit' in url:
        return url.split('/edit')[0] + '/export?format=csv'
    return url

@st.cache_data(ttl=3600)
def load_csv_data(url):
    """구글 시트에서 CSV 데이터 읽기 (인코딩 문제 해결)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        
        # BOM 제거 후 UTF-8로 강제 디코딩
        content = response.content
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]  # BOM 제거
        
        # BytesIO를 사용해 바이트 데이터를 직접 pandas에 전달하고 UTF-8 명시
        try:
            df = pd.read_csv(BytesIO(content), encoding='utf-8')
            return df, "UTF-8"
        except UnicodeDecodeError:
            # UTF-8 실패 시 다른 인코딩들 시도
            encodings = ['utf-8-sig', 'cp949', 'euc-kr']
            for encoding in encodings:
                try:
                    df = pd.read_csv(BytesIO(content), encoding=encoding)
                    return df, encoding
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            
            # 모든 인코딩 실패 시 에러 처리
            return None, "encoding_error"
            
    except Exception as e:
        return None, str(e)

def fix_broken_korean(text):
    """깨진 한글 패턴 복구"""
    if not isinstance(text, str):
        return text
    
    # 일반적인 깨진 한글 패턴들을 정상 한글로 복구
    korean_fixes = {
        'ì¬ê³¼': '사과', 'ì±': '책', 'íë³µí': '행복한', 'ë¬¼': '물',
        'ê³µë¶íë¤': '공부하다', 'ìì´': '영어', 'íêµ­ì´': '한국어',
        'ì»´í¨í°': '컴퓨터', 'íêµ': '학교', 'ì§': '집', 'ì°¨': '차',
        'ì¬ë': '사람', 'ìê°': '시간', 'ê³µë¶': '공부', 'íìµ': '학습',
        'ìë¦ë¤ì´': '아름다운', 'ì¢ì': '좋은'
    }
    
    for broken, fixed in korean_fixes.items():
        text = text.replace(broken, fixed)
    
    return text

def generate_audio(text, lang):
    """텍스트를 음성으로 변환하고 오디오 바이트 반환"""
    if not text or str(text).strip() == "":
        return None
    
    try:
        tts = gTTS(text=str(text).strip(), lang=lang)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        tts.save(temp_file.name)
        
        with open(temp_file.name, 'rb') as f:
            audio_bytes = f.read()
        
        os.unlink(temp_file.name)
        return audio_bytes
        
    except Exception as e:
        st.error(f"음성 생성 오류: {e}")
        return None

# 🚀 앱 시작 시 자동으로 데이터 로드
def auto_load_data():
    """앱 시작 시 자동으로 구글 시트 데이터 로드"""
    if not st.session_state.data_loaded:
        with st.spinner("📡 구글 시트에서 단어 데이터를 자동으로 불러오는 중..."):
            csv_url = convert_sheet_url(GOOGLE_SHEET_URL)
            result = load_csv_data(csv_url)
            
            if isinstance(result, tuple):
                data, encoding_info = result
            else:
                data, encoding_info = result, "unknown"
            
            if data is not None:
                # 컬럼 정규화
                column_mapping = {}
                for col in data.columns:
                    normalized_col = str(col).strip().lower()
                    if normalized_col in ['word', 'words', '단어']:
                        column_mapping['Word'] = col
                    elif normalized_col in ['meaning', 'meanings', '뜻']:
                        column_mapping['Meaning'] = col
                
                if 'Word' in column_mapping and 'Meaning' in column_mapping:
                    data = data.rename(columns={
                        column_mapping['Word']: 'Word',
                        column_mapping['Meaning']: 'Meaning'
                    })[['Word', 'Meaning']].copy()
                    
                    # 깨진 한글 복구 시도
                    data['Word'] = data['Word'].apply(fix_broken_korean)
                    data['Meaning'] = data['Meaning'].apply(fix_broken_korean)
                    
                    data = data.dropna().reset_index(drop=True)
                    data = data[data['Word'].str.strip() != ''].reset_index(drop=True)
                    
                    st.session_state.vocab_data = data
                    st.session_state.current_index = 0
                    st.session_state.data_loaded = True
                    
                    st.success(f"✅ 자동으로 {len(data)}개 단어를 불러왔습니다! ({encoding_info} 인코딩)")
                    return True
                else:
                    st.error("❌ 구글 시트에 'Word'와 'Meaning' 컬럼이 필요합니다!")
                    return False
            else:
                st.error(f"❌ 데이터 로드 실패: {encoding_info}")
                st.info("구글 시트가 '웹에 게시' 되어 있는지 확인해주세요.")
                return False
    return True

# 메인 UI
st.title("🎓 영어 단어장 학습 시스템")
st.markdown("**구글 시트 자동 연결 버전 - 바로 시작하세요!**")

# 🚀 자동 데이터 로드 실행
auto_load_data()

st.markdown("---")

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 설정")
    
    # 현재 연결된 시트 정보 표시
    with st.expander("📋 연결된 구글 시트", expanded=False):
        st.code(GOOGLE_SHEET_URL[:60] + "...", language=None)
        st.caption("💡 시트 주소는 코드에 하드코딩되어 있습니다")
        
        # 수동 새로고침 버튼
        if st.button("🔄 데이터 새로고침", use_container_width=True):
            # 캐시 클리어 후 다시 로드
            st.cache_data.clear()
            st.session_state.data_loaded = False
            st.rerun()
    
    # 학습 설정
    if st.session_state.vocab_data is not None:
        with st.expander("🎯 학습 설정", expanded=True):
            if st.button("🔀 순서 섞기", use_container_width=True):
                st.session_state.vocab_data = st.session_state.vocab_data.sample(frac=1).reset_index(drop=True)
                st.session_state.current_index = 0
                st.success("순서를 섞었습니다!")
            
            # 빠른 이동
            if len(st.session_state.vocab_data) > 0:
                st.markdown("**🎯 빠른 이동:**")
                quick_jump = st.selectbox(
                    "단어 선택:",
                    range(len(st.session_state.vocab_data)),
                    format_func=lambda x: f"{x+1}. {st.session_state.vocab_data.iloc[x]['Word']}",
                    index=st.session_state.current_index
                )
                if quick_jump != st.session_state.current_index:
                    st.session_state.current_index = quick_jump
                    st.rerun()

# 메인 영역
if st.session_state.vocab_data is not None:
    data = st.session_state.vocab_data
    current_idx = st.session_state.current_index
    
    # 진행률 표시
    progress = (current_idx + 1) / len(data)
    st.progress(progress)
    st.markdown(f"**📊 진행률: {current_idx + 1}/{len(data)} ({progress*100:.1f}%)**")
    
    # 현재 단어 표시
    if current_idx < len(data):
        word_data = data.iloc[current_idx]
        
        # 단어 카드 스타일
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            border-radius: 15px;
            margin: 20px 0;
            text-align: center;
            color: white;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        ">
            <h1 style="margin: 0; font-size: 3em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">{word_data['Word']}</h1>
            <hr style="border: 1px solid rgba(255,255,255,0.3);">
            <h2 style="margin: 0; font-size: 2em; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">{word_data['Meaning']}</h2>
        </div>
        """, unsafe_allow_html=True)
        
        # 음성 재생 버튼
        st.markdown("### 🔊 음성 듣기")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🇺🇸 영어 듣기", use_container_width=True, type="primary"):
                with st.spinner(f"🔊 '{word_data['Word']}' 음성 생성 중..."):
                    audio_bytes = generate_audio(word_data['Word'], 'en')
                    if audio_bytes:
                        st.audio(audio_bytes, format="audio/mp3")
        
        with col2:
            if st.button("🇰🇷 한국어 듣기", use_container_width=True, type="primary"):
                with st.spinner(f"🔊 '{word_data['Meaning']}' 음성 생성 중..."):
                    audio_bytes = generate_audio(word_data['Meaning'], 'ko')
                    if audio_bytes:
                        st.audio(audio_bytes, format="audio/mp3")
        
        with col3:
            if st.button("🎵 둘 다 듣기", use_container_width=True, type="secondary"):
                with st.spinner("🔊 영어와 한국어 음성 생성 중..."):
                    # 영어 먼저
                    audio_en = generate_audio(word_data['Word'], 'en')
                    if audio_en:
                        st.write("🇺🇸 영어:")
                        st.audio(audio_en, format="audio/mp3")
                    
                    # 한국어
                    audio_ko = generate_audio(word_data['Meaning'], 'ko')
                    if audio_ko:
                        st.write("🇰🇷 한국어:")
                        st.audio(audio_ko, format="audio/mp3")
        
        # 네비게이션 버튼
        st.markdown("---")
        st.markdown("### 🎯 학습 네비게이션")
        nav_col1, nav_col2, nav_col3, nav_col4 = st.columns(4)
        
        with nav_col1:
            if st.button("⏮️ 이전", disabled=(current_idx == 0), use_container_width=True):
                st.session_state.current_index = max(0, current_idx - 1)
                st.rerun()
        
        with nav_col2:
            if st.button("⏭️ 다음", disabled=(current_idx >= len(data) - 1), use_container_width=True):
                st.session_state.current_index = min(len(data) - 1, current_idx + 1)
                st.rerun()
        
        with nav_col3:
            if st.button("🔄 처음부터", use_container_width=True):
                st.session_state.current_index = 0
                st.rerun()
        
        with nav_col4:
            if st.button("📊 완료!", use_container_width=True):
                st.balloons()
                st.success(f"🎉 현재까지 {current_idx + 1}개 단어를 학습했습니다!")
                st.info(f"전체 진행률: {progress*100:.1f}%")

    # 단어 목록 표시
    with st.expander("📚 전체 단어 목록 보기"):
        # 검색 기능 추가
        search_term = st.text_input("🔍 단어 검색:", placeholder="검색할 영어 단어나 한국어 뜻 입력")
        
        if search_term:
            filtered_data = data[
                data['Word'].str.contains(search_term, case=False, na=False) |
                data['Meaning'].str.contains(search_term, case=False, na=False)
            ]
            st.write(f"검색 결과: {len(filtered_data)}개")
            st.dataframe(filtered_data, use_container_width=True)
        else:
            st.dataframe(data, use_container_width=True)

else:
    # 데이터 로드 실패 시 안내
    st.markdown("""
    ## ❌ 데이터 로드 실패
    
    구글 시트에서 데이터를 불러올 수 없습니다.
    
    ### 🔍 확인사항:
    1. **구글 시트가 '웹에 게시' 되어 있는지 확인**
    2. **시트의 첫 번째 행이 'Word', 'Meaning'인지 확인**
    3. **인터넷 연결 상태 확인**
    
    ### 📋 올바른 구글 시트 형식:
    
    | Word | Meaning |
    |------|---------|
    | apple | 사과 |
    | book | 책 |
    | happy | 행복한 |
    
    ### 🔄 해결 방법:
    1. 구글 시트에서 **파일 → 웹에 게시** 클릭
    2. **"쉼표로 구분된 값(.csv)"** 선택
    3. **게시** 클릭
    4. 왼쪽 사이드바의 **"데이터 새로고침"** 버튼 클릭
    """)

st.markdown("---")
st.caption("🚀 Powered by Streamlit + Google Sheets + AI | 자동 연결 버전")

# 하단에 현재 설정된 시트 URL 표시 (개발자용)
with st.expander("🔧 개발자 정보", expanded=False):
    st.code(f"GOOGLE_SHEET_URL = '{GOOGLE_SHEET_URL}'", language="python")
    st.caption("💡 시트 주소를 변경하려면 코드의 GOOGLE_SHEET_URL 변수를 수정하세요.")
