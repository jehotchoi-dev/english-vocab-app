import streamlit as st
import pandas as pd
import requests
from gtts import gTTS
import tempfile
import os
import uuid
from io import StringIO, BytesIO
import base64
import time
import re
import logging
import datetime 

# ========================
# 🔧 설정: 하드코딩된 구글 시트 링크
# ========================
# 👇 여기에 자신의 구글 시트 공개 CSV 링크를 입력하세요.
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTZltgfm_yfhVNBHaK8Aj1oQArXZhn8woXNn9hM_NIjryHQeVgkt3KP3xEx6h-IlHVFFlbxgQS2l5A5/pub?output=csv"

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 페이지 설정
st.set_page_config(
    page_title="🎓 영어 단어장",
    page_icon="📚",
    layout="wide"
)

# ========================
# 세션 상태 초기화
# ========================
if 'vocab_data' not in st.session_state:
    st.session_state.vocab_data = None
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'audio_cache' not in st.session_state:
    st.session_state.audio_cache = {}

# ========================
# 🚀 데이터 로드 및 처리 함수
# ========================

def convert_sheet_url(original_url: str) -> str:
    """구글 시트 링크를 CSV 형식으로 변환"""
    url = original_url.strip()
    if 'output=csv' in url:
        return url
    if 'pubhtml' in url:
        return url.replace('pubhtml', 'pub?output=csv')
    if '/edit' in url:
        return url.split('/edit')[0] + '/export?format=csv'
    return url

# 👇 TTL을 300초(5분)로 단축하여 데이터 새로고침 주기 설정
@st.cache_data(ttl=300) 
def load_csv_data(url: str):
    """구글 시트에서 CSV 데이터 읽기 (인코딩 최적화 및 5분 캐시 적용)"""
    start_time = time.time()
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        content = response.content
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]  # BOM 제거
        
        # 다양한 인코딩 시도
        for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']:
            try:
                df = pd.read_csv(BytesIO(content), encoding=encoding)
                logger.info(f"Data decoded with {encoding}. Time taken: {time.time() - start_time:.2f}s")
                return df
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        
        st.error("지원하는 인코딩으로 파일을 읽을 수 없습니다.")
        return None
        
    except Exception as e:
        logger.error(f"데이터 읽기 오류 (URL: {url}): {e}")
        return None

def fix_broken_korean(text):
    """깨진 한글 패턴 복구"""
    if not isinstance(text, str):
        return text
    
    try:
        text = text.encode('latin1').decode('utf-8')
    except:
        pass 

    korean_fixes = {
        'ì¬ê³¼': '사과', 'ì±': '책', 'íë³µí': '행복한', 'ë¬¼': '물',
        'ê³µë¶íë¤': '공부하다', 'ìì´': '영어', 'íêµ­ì´': '한국어',
        'ì»´í¨í°': '컴퓨터', 'íêµ': '학교', 'ì§': '집', 'ì°¨': '차',
        'ì¬ë': '사람', 'ìê°': '시간', 'ê³µë¶': '공부', 'íìµ': '학습'
    }
    
    for broken, fixed in korean_fixes.items():
        text = text.replace(broken, fixed)
    return text

def sanitize_english_text(text: str) -> str:
    """영어 텍스트 정리: 유효한 문자만 추출"""
    if not text:
        return ""
    
    # 알파벳, 숫자, 공백, 하이픈, 아포스트로피, 쉼표, 점만 허용
    clean_text = re.sub(r'[^a-zA-Z0-9\s\-\',\.]', '', str(text))
    return clean_text.strip()

# ========================
# 🔊 TTS 및 오디오 재생 함수
# ========================

def generate_audio_bytes(text: str, lang: str = 'en', max_retries: int = 3):
    """텍스트를 음성으로 변환 (재시도 로직 및 오류 처리 포함)"""
    if not text or str(text).strip() == "":
        logger.warning(f"Empty text provided for audio generation: '{text}'")
        return None
    
    clean_text = str(text).strip()
    if lang == 'en':
        clean_text = sanitize_english_text(clean_text)
        if not clean_text:
            logger.warning(f"No valid English characters after cleaning: '{text}'")
            return None
    
    last_error = None
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(1) 
                logger.info(f"Retrying audio generation for '{clean_text}', attempt {attempt
