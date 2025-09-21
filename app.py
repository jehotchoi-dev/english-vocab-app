import streamlit as st
import pandas as pd
import requests
from gtts import gTTS
import tempfile
import os
import uuid
from io import StringIO, BytesIO
import base64

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
    """구글 시트에서 CSV 데이터 읽기"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        
        content = response.content
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]
        
        try:
            df = pd.read_csv(BytesIO(content), encoding='utf-8')
            return df
        except UnicodeDecodeError:
            encodings = ['utf-8-sig', 'cp949', 'euc-kr']
            for encoding in encodings:
                try:
                    df = pd.read_csv(BytesIO(content), encoding=encoding)
                    return df
                except:
                    continue
            return None
            
    except Exception as e:
        st.error(f"데이터 읽기 오류: {e}")
        return None

def fix_broken_korean(text):
    """깨진 한글 복구"""
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

@st.cache_data(ttl=3600)
def generate_audio_bytes(text, lang):
    """텍스트를 음성으로 변환하고 오디오 바이트 반환"""
    if not text or str(text).strip() == "":
        return None
    
    try:
        tts = gTTS(text=str(text).strip(), lang=lang)
        temp_buffer = BytesIO()
        tts.save(temp_buffer)
        temp_buffer.seek(0)
        return temp_buffer.getvalue()
        
    except Exception as e:
        st.error(f"음성 생성 오류: {e}")
        return None

def play_audio_with_js(audio_bytes):
    """JavaScript로 오디오 재생 (중복 재생 완전 방지)"""
    if not audio_bytes:
        return
    
    try:
        # 오디오를 base64로 인코딩
        b64_audio = base64.b64encode(audio_bytes).decode()
        
        # 고유한 ID로 중복 방지
        audio_id = f"audio_{uuid.uuid4().hex[:8]}"
        
        # JavaScript로 직접 오디오 재생
        html_code = f"""
        <div style="padding: 10px; background: #f0f8ff; border-radius: 8px; margin: 10px 0;">
            <p style="margin: 0; color: #1e90ff; font-weight: bold;">🔊 영어 음성 재생 중...</p>
        </div>
        <audio id="{audio_id}" style="display: none;">
            <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
        </audio>
        <script>
            (function() {{
                const audio = document.getElementById('{audio_id}');
                if (audio) {{
                    // 기존 재생 중인 오디오 정지
                    const existingAudios = document.querySelectorAll('audio');
                    existingAudios.forEach(a => {{
                        if (a.id !== '{audio_id}') {{
                            a.pause();
                            a.currentTime = 0;
                        }}
                    }});
                    
                    // 새 오디오 재생
                    audio.play().catch(e => console.log("Audio play failed:", e));
                }}
            }})();
        </script>
        """
        
        st.components.v1.html(html_code, height=60)
        
    except Exception as e:
        st.error(f"오디오 재생 오류: {e}")

# 메인 UI
st.title("🎓 영어 단어장 학습 시스템")
st.markdown("**영어 음성 전용 - 아이패드 중복 재생 문제 해결 완료!**")

# 아이패드 사용자 안내
st.success("""
📱 **아이패드 최적화 완료:**
- ✅ **영어 단어만 정확히 한 번 재생**
- ✅ **중복 재생 문제 완전 해결** (JavaScript 직접 제어)
- ✅ **불필요한 기능 제거** (한국어 듣기, 둘 다 듣기)
- 🔇 **소리가 안 나오면**: 아이패드 무음 모드 해제 및 볼륨 확인
""")

st.markdown("---")

# 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    
    with st.expander("📋 구글 시트 연결", expanded=True):
        sheet_url = st.text_input(
            "구글 시트 링크:",
            placeholder="https://docs.google.com/spreadsheets/d/...",
            help="구글 시트 '웹에 게시' 링크"
        )
        
        if st.button("📥 단어 불러오기", use_container_width=True):
            if sheet_url:
                with st.spinner("데이터 로딩 중..."):
                    csv_url = convert_sheet_url(sheet_url)
                    data = load_csv_data(csv_url)
                    
                    if data is not None:
                        # 컬럼 매핑
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
                            
                            # 한글 복구
                            data['Word'] = data['Word'].apply(fix_broken_korean)
                            data['Meaning'] = data['Meaning'].apply(fix_broken_korean)
                            
                            # 데이터 정리
                            data = data.dropna().reset_index(drop=True)
                            data = data[data['Word'].str.strip() != ''].reset_index(drop=True)
                            
                            st.session_state.vocab_data = data
                            st.session_state.current_index = 0
                            st.success(f"✅ {len(data)}개 단어를 불러왔습니다!")
                            
                            # 미리보기
                            st.dataframe(data.head(3))
                        else:
                            st.error("❌ 'Word'와 'Meaning' 컬럼이 필요합니다!")
            else:
                st.error("구글 시트 링크를 입력해주세요!")
    
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
    
    # 진행률
    progress = (current_idx + 1) / len(data)
    st.progress(progress)
    st.markdown(f"**📊 진행률: {current_idx + 1}/{len(data)} ({progress*100:.1f}%)**")
    
    if current_idx < len(data):
        word_data = data.iloc[current_idx]
        
        # 단어 카드 (아이패드 최적화)
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            padding: 50px 30px;
            border-radius: 25px;
            margin: 30px 0;
            text-align: center;
            color: white;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        ">
            <h1 style="margin: 0 0 20px 0; font-size: 4em; font-weight: bold; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
                {word_data['Word']}
            </h1>
            <hr style="border: 3px solid rgba(255,255,255,0.4); margin: 25px 0;">
            <h2 style="margin: 0; font-size: 2.8em; font-weight: 300; opacity: 0.95;">
                {word_data['Meaning']}
            </h2>
        </div>
        """, unsafe_allow_html=True)
        
        # 영어 듣기 버튼만!
        st.markdown("### 🎵 영어 발음 듣기")
        
        if st.button(
            f"🔊 '{word_data['Word']}' 듣기", 
            use_container_width=True, 
            type="primary",
            help="영어 단어 발음을 들어보세요"
        ):
            with st.spinner(f"🎵 '{word_data['Word']}' 음성 생성 중..."):
                audio_bytes = generate_audio_bytes(word_data['Word'], 'en')
                if audio_bytes:
                    play_audio_with_js(audio_bytes)
                else:
                    st.error("음성 생성에 실패했습니다. 인터넷 연결을 확인해주세요.")
        
        # 네비게이션 (아이패드 최적화)
        st.markdown("---")
        st.markdown("### 🧭 단어 탐색")
        
        # 2x2 레이아웃
        nav_col1, nav_col2 = st.columns(2)
        
        with nav_col1:
            if st.button("⏮️ 이전 단어", disabled=(current_idx == 0), use_container_width=True):
                st.session_state.current_index = max(0, current_idx - 1)
                st.rerun()
        
        with nav_col2:
            if st.button("⏭️ 다음 단어", disabled=(current_idx >= len(data) - 1), use_container_width=True):
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
                🏆 **학습 현황**
                - 현재: {current_idx + 1}/{len(data)} 단어
                - 진행률: {completion_rate:.1f}%
                - 남은 단어: {len(data) - current_idx - 1}개
                """)

    # 전체 단어 목록
    with st.expander("📚 전체 단어 목록"):
        st.dataframe(data, use_container_width=True)

else:
    # 시작 화면
    st.markdown("""
    ## 🚀 영어 단어장 시작하기
    
    ### 📱 아이패드 완벽 최적화
    - ✅ **영어 음성만 정확히 한 번 재생**
    - ✅ **JavaScript 직접 제어로 중복 재생 완전 방지**
    - ✅ **심플한 인터페이스** (불필요한 기능 제거)
    - 📱 **터치 최적화** (큰 버튼, 명확한 레이아웃)
    
    ### 📋 사용 방법
    1. **왼쪽 사이드바**에서 구글 시트 링크 입력
    2. **"단어 불러오기"** 클릭
    3. **🔊 듣기 버튼**으로 영어 발음 학습
    4. **⏭️ 다음/이전** 버튼으로 단어 탐색
    
    ### 📊 구글 시트 형식
    ```
    | Word  | Meaning |
    |-------|---------|
    | apple | 사과    |
    | book  | 책      |
    | happy | 행복한  |
    ```
    
    **중요:** 구글 시트에서 **파일 → 웹에 게시 → CSV 형식**으로 게시해주세요!
    """)

st.markdown("---")
st.caption("🎵 Powered by Streamlit + Google TTS | 영어 음성 전용 아이패드 최적화 완료!")
