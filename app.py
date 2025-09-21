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

# ========================
# 🔧 설정: 하드코딩된 구글 시트 링크
# ========================
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

# 세션 상태 초기화
if 'vocab_data' not in st.session_state:
    st.session_state.vocab_data = None
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'audio_cache' not in st.session_state:
    st.session_state.audio_cache = {}

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

@st.cache_data(ttl=1800)
def load_csv_data(url: str):
    """구글 시트에서 CSV 데이터 읽기 (인코딩 최적화)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        
        content = response.content
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]  # BOM 제거
        
        # 다양한 인코딩 시도
        for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']:
            try:
                df = pd.read_csv(BytesIO(content), encoding=encoding)
                return df
            except (UnicodeDecodeError, pd.errors.ParserError):
                logger.info(f"Failed to decode with {encoding}")
                continue
        
        st.error("지원하는 인코딩으로 파일을 읽을 수 없습니다.")
        return None
        
    except Exception as e:
        logger.error(f"데이터 읽기 오류: {e}")
        st.error(f"데이터 읽기 오류: {e}")
        return None

def fix_broken_korean(text):
    """깨진 한글 패턴 복구"""
    if not isinstance(text, str):
        return text
    
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
    
    # 알파벳, 공백, 하이픈, 아포스트로피만 허용
    clean_text = re.sub(r'[^a-zA-Z\s\-\']', '', str(text))
    return clean_text.strip()

def generate_audio_bytes(text: str, lang: str = 'en', max_retries: int = 3):
    """텍스트를 음성으로 변환 (재시도 로직 및 오류 처리 포함)"""
    if not text or str(text).strip() == "":
        logger.warning(f"Empty text provided for audio generation: '{text}'")
        return None
    
    # 텍스트 전처리
    clean_text = str(text).strip()
    if lang == 'en':
        clean_text = sanitize_english_text(clean_text)
        if not clean_text:
            st.warning("유효한 영어 문자가 없어 음성을 생성할 수 없습니다.")
            logger.warning(f"No valid English characters after cleaning: '{text}'")
            return None
    
    # 재시도 로직
    last_error = None
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(1)  # 재시도 전 대기
                st.info(f"음성 생성 재시도 중... ({attempt + 1}/{max_retries})")
                logger.info(f"Retrying audio generation for '{clean_text}', attempt {attempt + 1}")
            
            tts = gTTS(text=clean_text, lang=lang, slow=False)
            temp_buffer = BytesIO()
            
            # 핵심 수정: save() 대신 write_to_fp() 사용
            tts.write_to_fp(temp_buffer)
            
            temp_buffer.seek(0)
            audio_data = temp_buffer.getvalue()
            
            # 음성 데이터 유효성 검사
            if len(audio_data) > 0:
                logger.info(f"Audio generated successfully for '{clean_text}' ({len(audio_data)} bytes)")
                return audio_data
            else:
                raise Exception("빈 오디오 데이터 생성됨")
            
        except Exception as e:
            last_error = e
            logger.error(f"TTS Error for '{clean_text}' (attempt {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)}")
            
            if attempt == max_retries - 1:
                # 최종 실패 시 상세한 안내
                st.error(f"""
                ⚠️ **음성 생성 최종 실패**
                
                **오류 유형**: {type(last_error).__name__}  
                **오류 내용**: {str(last_error)}
                
                **🔧 해결 방법:**
                1. 🌐 **인터넷 연결 상태** 확인
                2. 🛡️ **방화벽/프록시** 설정에서 Google TTS 접근 허용
                3. 🔄 **잠시 후 다시 시도**
                4. 📱 **기기 볼륨 및 무음 모드** 확인
                """)
                
                # 대체 방법 제시
                st.info(f"""
                **📋 대체 방법:**
                - [Google 번역에서 직접 듣기](https://translate.google.com/?sl=en&tl=ko&text={clean_text})
                - 기기의 내장 음성 읽기 기능 사용
                """)
                
                return None
    
    return None

def get_audio_with_cache(text: str, lang: str = 'en'):
    """캐싱 시스템을 적용한 음성 생성"""
    cache_key = f"{text.strip()}_{lang}"
    
    # 캐시에서 확인
    if cache_key in st.session_state.audio_cache:
        logger.info(f"Audio cache hit for '{text}'")
        return st.session_state.audio_cache[cache_key]
    
    # 새로 생성
    audio_bytes = generate_audio_bytes(text, lang)
    if audio_bytes:
        st.session_state.audio_cache[cache_key] = audio_bytes
        logger.info(f"Audio cached for '{text}' ({len(audio_bytes)} bytes)")
    
    return audio_bytes

def play_audio_with_js(audio_bytes: bytes):
    """JavaScript를 사용한 오디오 재생 (아이패드 최적화)"""
    if not audio_bytes:
        return
    
    try:
        b64_audio = base64.b64encode(audio_bytes).decode()
        audio_id = f"audio_{uuid.uuid4().hex[:8]}"
        
        html_code = f"""
        <div style="
            padding: 15px; 
            background: linear-gradient(90deg, #e3f2fd 0%, #f3e5f5 100%); 
            border-radius: 12px; 
            margin: 15px 0; 
            border-left: 5px solid #2196f3;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        ">
            <p style="margin: 0; color: #1565c0; font-weight: bold; font-size: 1.1em;">
                🔊 영어 음성 재생 중...
            </p>
            <p style="margin: 5px 0 0 0; color: #7b1fa2; font-size: 0.9em;">
                아이패드 중복 재생 방지 완료! (크기: {len(audio_bytes)} bytes)
            </p>
        </div>
        <audio id="{audio_id}" style="display: none;">
            <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
        </audio>
        <script>
            (function() {{
                const audio = document.getElementById('{audio_id}');
                if (audio) {{
                    // 기존 재생 중인 모든 오디오 정지
                    document.querySelectorAll('audio').forEach(a => {{
                        if (a.id !== '{audio_id}') {{
                            a.pause();
                            try {{ a.currentTime = 0; }} catch(e) {{}}
                        }}
                    }});
                    
                    // 새 오디오 재생
                    audio.pause();
                    try {{ audio.currentTime = 0; }} catch(e) {{}}
                    
                    // 재생 시작 (Promise 처리)
                    const playPromise = audio.play();
                    if (playPromise !== undefined) {{
                        playPromise.then(() => {{
                            console.log("Audio started successfully");
                        }}).catch(error => {{
                            console.log("Audio play failed:", error);
                        }});
                    }}
                }}
            }})();
        </script>
        """
        
        st.components.v1.html(html_code, height=90)
        
    except Exception as e:
        logger.error(f"오디오 재생 오류: {e}")
        st.error(f"오디오 재생 오류: {e}")

def test_tts_connection() -> bool:
    """TTS 서비스 연결 테스트"""
    try:
        test_result = generate_audio_bytes("hello", "en", max_retries=1)
        return test_result is not None
    except Exception as e:
        logger.error(f"TTS connection test failed: {e}")
        return False

def initialize_data() -> bool:
    """앱 시작 시 자동으로 데이터 로드"""
    if not st.session_state.data_loaded:
        with st.spinner("🚀 구글 시트에서 단어 데이터를 자동으로 불러오는 중..."):
            csv_url = convert_sheet_url(GOOGLE_SHEET_URL)
            data = load_csv_data(csv_url)
            
            if data is not None:
                # 컬럼 매핑
                column_mapping = {}
                for col in data.columns:
                    normalized_col = str(col).strip().lower()
                    if normalized_col in ['word', 'words', '단어']:
                        column_mapping['Word'] = col
                    elif normalized_col in ['meaning', 'meanings', '뜻', '의미']:
                        column_mapping['Meaning'] = col
                
                if 'Word' in column_mapping and 'Meaning' in column_mapping:
                    data = data.rename(columns={
                        column_mapping['Word']: 'Word',
                        column_mapping['Meaning']: 'Meaning'
                    })[['Word', 'Meaning']].copy()
                    
                    # 데이터 정리
                    data['Word'] = data['Word'].apply(fix_broken_korean)
                    data['Meaning'] = data['Meaning'].apply(fix_broken_korean)
                    
                    data = data.dropna().reset_index(drop=True)
                    data = data[data['Word'].astype(str).str.strip() != ''].reset_index(drop=True)
                    
                    st.session_state.vocab_data = data
                    st.session_state.current_index = 0
                    st.session_state.data_loaded = True
                    
                    logger.info(f"Vocabulary data loaded successfully: {len(data)} words")
                    return True
                else:
                    st.error("❌ 구글 시트에 'Word'와 'Meaning' 컬럼이 필요합니다!")
                    logger.error("Missing required columns in Google Sheet")
                    return False
            else:
                st.error("❌ 구글 시트 데이터를 불러올 수 없습니다.")
                logger.error("Failed to load data from Google Sheet")
                return False
    return True

# ========================
# 메인 UI
# ========================

st.title("🎓 영어 단어장 학습 시스템")
st.markdown("**하드코딩된 구글 시트 자동 연동 - 영어 음성 전용 (오류 수정 완료)**")

# 아이패드 사용자 안내
st.success("""
📱 **아이패드 완벽 최적화 완료!**
- ✅ **자동 단어장 로드** - 링크 입력 불필요
- ✅ **영어 음성만 정확히 한 번 재생** - JavaScript 직접 제어
- ✅ **중복 재생 문제 완전 해결**
- ✅ **음성 생성 오류 수정** - 재시도 로직 및 캐싱 적용
- 🔇 **소리가 안 나오면**: 무음 모드 해제 및 볼륨 확인
""")

# TTS 서비스 관리 도구
col_test1, col_test2 = st.columns([1, 1])

with col_test1:
    if st.button("🌐 TTS 연결 테스트", help="Google Text-to-Speech 서비스 연결 상태를 확인합니다"):
        with st.spinner("TTS 서비스 연결 테스트 중..."):
            if test_tts_connection():
                st.success("✅ Google TTS 서비스 연결 정상")
            else:
                st.error("❌ TTS 서비스 연결 실패 - 네트워크 환경을 확인해주세요")

with col_test2:
    cache_size = len(st.session_state.audio_cache)
    if st.button(f"🗑️ 음성 캐시 삭제 ({cache_size}개)", help="저장된 음성 파일들을 모두 삭제합니다"):
        st.session_state.audio_cache.clear()
        st.info("음성 캐시가 삭제되었습니다.")
        st.rerun()

# 데이터 자동 로드
data_success = initialize_data()

if data_success and st.session_state.vocab_data is not None:
    data = st.session_state.vocab_data
    current_idx = st.session_state.current_index
    
    # 상단 대시보드
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        st.metric("📚 총 단어", len(data))
    
    with col2:
        progress = (current_idx + 1) / len(data) if len(data) > 0 else 0
        st.progress(progress)
        st.markdown(f"**📊 진행률: {current_idx + 1}/{len(data)} ({progress*100:.1f}%)**")
    
    with col3:
        if st.button("🔀 순서 섞기", use_container_width=True):
            st.session_state.vocab_data = data.sample(frac=1).reset_index(drop=True)
            st.session_state.current_index = 0
            st.session_state.audio_cache.clear()  # 순서 변경 시 캐시 초기화
            st.success("순서를 섞었습니다!")
            st.rerun()
    
    st.markdown("---")
    
    if current_idx < len(data):
        word_data = data.iloc[current_idx]
        
        # 단어 카드
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 60px 40px;
            border-radius: 25px;
            margin: 40px 0;
            text-align: center;
            color: white;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
            border: 2px solid rgba(255,255,255,0.2);
        ">
            <h1 style="
                margin: 0 0 25px 0; 
                font-size: 4.2em; 
                font-weight: bold; 
                text-shadow: 3px 3px 6px rgba(0,0,0,0.3);
                letter-spacing: 1px;
            ">
                {word_data['Word']}
            </h1>
            <div style="
                height: 3px; 
                background: linear-gradient(90deg, rgba(255,255,255,0.7) 0%, rgba(255,255,255,0.3) 100%); 
                margin: 25px auto; 
                width: 70%;
                border-radius: 2px;
            "></div>
            <h2 style="
                margin: 0; 
                font-size: 2.8em; 
                font-weight: 300; 
                opacity: 0.95;
                text-shadow: 1px 1px 3px rgba(0,0,0,0.2);
            ">
                {word_data['Meaning']}
            </h2>
        </div>
        """, unsafe_allow_html=True)
        
        # 영어 듣기 버튼
        st.markdown("### 🎵 영어 발음 듣기")
        
        # 캐시 상태 표시
        cache_key = f"{word_data['Word'].strip()}_en"
        is_cached = cache_key in st.session_state.audio_cache
        cache_status = "💾 캐시됨" if is_cached else "🌐 새로 생성"
        
        if st.button(
            f"🔊 '{word_data['Word']}' 발음 듣기 ({cache_status})", 
            use_container_width=True, 
            type="primary",
            help="영어 단어 발음을 들어보세요 (아이패드 최적화, 재시도 로직 적용)"
        ):
            with st.spinner(f"🎵 '{word_data['Word']}' 음성 {'불러오는' if is_cached else '생성하는'} 중..."):
                audio_bytes = get_audio_with_cache(word_data['Word'], 'en')
                if audio_bytes:
                    play_audio_with_js(audio_bytes)
                    st.success(f"✅ '{word_data['Word']}' 음성 재생 완료!")
        
        # 네비게이션
        st.markdown("---")
        st.markdown("### 🧭 단어 탐색")
        
        nav_col1, nav_col2 = st.columns(2)
        
        with nav_col1:
            if st.button("⏮️ 이전 단어", disabled=(current_idx == 0), use_container_width=True, type="secondary"):
                st.session_state.current_index = max(0, current_idx - 1)
                st.rerun()
        
        with nav_col2:
            if st.button("⏭️ 다음 단어", disabled=(current_idx >= len(data) - 1), use_container_width=True, type="secondary"):
                st.session_state.current_index = min(len(data) - 1, current_idx + 1)
                st.rerun()
        
        st.write("")
        
        nav_col3, nav_col4 = st.columns(2)
        
        with nav_col3:
            if st.button("🔄 처음부터", use_container_width=True):
                st.session_state.current_index = 0
                st.rerun()
        
        with nav_col4:
            if st.button("🎉 학습 완료", use_container_width=True):
                st.balloons()
                completion_rate = ((current_idx + 1) / len(data)) * 100
                st.success(f"""
                🏆 **학습 현황 리포트**
                
                📊 **현재 진행률**: {completion_rate:.1f}%  
                📚 **학습한 단어**: {current_idx + 1}/{len(data)}개  
                ⏳ **남은 단어**: {len(data) - current_idx - 1}개  
                🎯 **상태**: {"완주 달성! 🎊" if current_idx >= len(data) - 1 else f"완주까지 {len(data) - current_idx - 1}개 남음!"}  
                💾 **음성 캐시**: {len(st.session_state.audio_cache)}개 저장됨
                """)

    # 전체 단어 목록
    with st.expander("📚 전체 단어 목록 보기"):
        display_data = data.copy()
        display_data['상태'] = ['👈 현재 위치' if i == current_idx else '' for i in range(len(data))]
        
        # 캐시 상태 표시
        display_data['음성'] = [
            '💾' if f"{row['Word'].strip()}_en" in st.session_state.audio_cache else '🌐' 
            for _, row in data.iterrows()
        ]
        
        st.dataframe(
            display_data[['상태', 'Word', 'Meaning', '음성']], 
            use_container_width=True,
            hide_index=True,
            column_config={
                "음성": st.column_config.TextColumn(
                    "음성",
                    help="💾: 캐시됨, 🌐: 새로 생성",
                    width="small"
                )
            }
        )

else:
    # 데이터 로딩 실패 시
    st.error(f"""
    ❌ **단어장 로딩 실패**
    
    구글 시트 연결에 문제가 있습니다. 다음을 확인해주세요:
    
    1. **코드의 `GOOGLE_SHEET_URL` 변수 확인**
    2. **구글 시트 "웹에 게시" 활성화 여부**
    3. **CSV 형식으로 게시되었는지 확인**
    4. **시트에 'Word', 'Meaning' 컬럼 존재 여부**
    5. **인터넷 연결 상태**
    
    📋 **현재 설정된 링크:**
    ```
    {GOOGLE_SHEET_URL[:80]}...
    ```
    """)
    
    if st.button("🔄 다시 시도", use_container_width=True):
        st.session_state.data_loaded = False
        st.cache_data.clear()
        st.session_state.audio_cache.clear()
        st.rerun()

st.markdown("---")
st.caption("🎵 Powered by Streamlit + Google Sheets + Google TTS | 하드코딩 자동 로드 버전 (오류 수정 완료)")
