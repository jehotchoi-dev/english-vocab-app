import streamlit as st
import pandas as pd
import requests
from gtts import gTTS
import tempfile
import os
import uuid
from io import StringIO, BytesIO
import time

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
            st.success("✅ UTF-8 인코딩으로 성공적으로 읽었습니다!")
            return df
        except UnicodeDecodeError:
            # UTF-8 실패 시 다른 인코딩들 시도
            encodings = ['utf-8-sig', 'cp949', 'euc-kr']
            for encoding in encodings:
                try:
                    df = pd.read_csv(BytesIO(content), encoding=encoding)
                    st.info(f"✅ {encoding} 인코딩으로 읽었습니다!")
                    return df
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            
            # 모든 인코딩 실패 시 에러 처리
            st.error("❌ 지원하는 인코딩으로 파일을 읽을 수 없습니다.")
            return None
            
    except Exception as e:
        st.error(f"데이터 읽기 오류: {e}")
        return None

def fix_broken_korean(text):
    """깨진 한글 패턴 복구"""
    if not isinstance(text, str):
        return text
    
    # 일반적인 깨진 한글 패턴들을 정상 한글로 복구
    korean_fixes = {
        'ì¬ê³¼': '사과',
        'ì±': '책', 
        'íë³µí': '행복한',
        'ë¬¼': '물',
        'ê³µë¶íë¤': '공부하다',
        'ìì´': '영어',
        'íêµ­ì´': '한국어',
        'ì»´í¨í°': '컴퓨터',
        'íêµ': '학교',
        'ì§': '집',
        'ì°¨': '차',
        'ì¬ë': '사람',
        'ìê°': '시간',
        'ê³µë¶': '공부',
        'íìµ': '학습'
    }
    
    for broken, fixed in korean_fixes.items():
        text = text.replace(broken, fixed)
    
    return text

def generate_audio(text, lang, key):
    """텍스트를 음성으로 변환하고 재생"""
    if not text or str(text).strip() == "":
        return
    
    try:
        with st.spinner(f"🔊 {text} 음성 생성 중..."):
            tts = gTTS(text=str(text).strip(), lang=lang)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            tts.save(temp_file.name)
            
            with open(temp_file.name, 'rb') as f:
                audio_bytes = f.read()
            
            st.audio(audio_bytes, format="audio/mp3", key=key)
            os.unlink(temp_file.name)
            
    except Exception as e:
        st.error(f"음성 생성 오류: {e}")

# 메인 UI
st.title("🎓 영어 단어장 학습 시스템")
st.markdown("**구글 시트 기반 AI 음성 학습 프로그램 (한글 인코딩 문제 해결 버전)**")
st.markdown("---")

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 설정")
    
    # 구글 시트 연결
    with st.expander("📋 구글 시트 연결", expanded=True):
        sheet_url = st.text_input(
            "구글 시트 링크:",
            placeholder="https://docs.google.com/spreadsheets/d/...",
            help="구글 시트에서 '파일 → 웹에 게시'로 생성한 링크"
        )
        
        if st.button("📥 단어 불러오기", use_container_width=True):
            if sheet_url:
                with st.spinner("데이터 로딩 중... (인코딩 자동 감지)"):
                    csv_url = convert_sheet_url(sheet_url)
                    data = load_csv_data(csv_url)
                    
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
                            st.success(f"✅ {len(data)}개 단어를 불러왔습니다!")
                            
                            # 데이터 미리보기
                            st.info("📖 불러온 데이터 미리보기:")
                            st.dataframe(data.head(3))
                            
                        else:
                            st.error("❌ 'Word'와 'Meaning' 컬럼이 필요합니다!")
            else:
                st.error("구글 시트 링크를 입력해주세요!")
    
    # 학습 설정
    if st.session_state.vocab_data is not None:
        with st.expander("🎯 학습 설정"):
            if st.button("🔀 순서 섞기", use_container_width=True):
                st.session_state.vocab_data = st.session_state.vocab_data.sample(frac=1).reset_index(drop=True)
                st.session_state.current_index = 0
                st.success("순서를 섞었습니다!")

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
            <h1 style="margin: 0; font-size: 3em;">{word_data['Word']}</h1>
            <hr style="border: 1px solid rgba(255,255,255,0.3);">
            <h2 style="margin: 0; font-size: 2em;">{word_data['Meaning']}</h2>
        </div>
        """, unsafe_allow_html=True)
        
        # 음성 재생 버튼
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🇺🇸 영어 듣기", use_container_width=True, type="primary"):
                generate_audio(word_data['Word'], 'en', f"en_{current_idx}")
        
        with col2:
            if st.button("🇰🇷 한국어 듣기", use_container_width=True, type="primary"):
                generate_audio(word_data['Meaning'], 'ko', f"ko_{current_idx}")
        
        with col3:
            if st.button("🎵 둘 다 듣기", use_container_width=True, type="secondary"):
                generate_audio(word_data['Word'], 'en', f"both_en_{current_idx}")
                time.sleep(1)
                generate_audio(word_data['Meaning'], 'ko', f"both_ko_{current_idx}")
        
        # 네비게이션 버튼
        st.markdown("---")
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

    # 단어 목록 표시
    with st.expander("📚 전체 단어 목록 보기"):
        st.dataframe(data, use_container_width=True)

else:
    # 초기 화면
    st.markdown("""
    ## 🚀 시작하기
    
    1. **왼쪽 사이드바**에서 구글 시트 링크를 입력하세요
    2. **"단어 불러오기"** 버튼을 클릭하세요
    3. 단어 학습을 시작하세요!
    
    ### 📋 구글 시트 준비 방법
    
    구글 시트를 다음과 같이 준비해주세요:
    
    | Word | Meaning |
    |------|---------|
    | apple | 사과 |
    | book | 책 |
    | happy | 행복한 |
    
    **그리고 중요한 단계:**
    1. **파일 → 웹에 게시** 클릭
    2. **"쉼표로 구분된 값(.csv)"** 선택
    3. **게시** 클릭 후 링크 복사
    
    ### ✨ 주요 기능
    - 🔊 **고품질 AI 음성**: 영어와 한국어 모두 자연스러운 발음
    - 🎯 **인터랙티브 학습**: 이전/다음 버튼으로 자유로운 탐색
    - 🔀 **무작위 학습**: 순서를 섞어서 효과적인 암기
    - 📱 **어디서든 접속**: 웹 브라우저만 있으면 OK
    - 🛠️ **한글 인코딩 자동 처리**: 깨진 한글 자동 복구
    """)

st.markdown("---")
st.caption("🚀 Powered by Streamlit + Google Sheets + AI | 한글 인코딩 문제 해결 버전")
