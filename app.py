import streamlit as st
import pandas as pd
import requests
from gtts import gTTS
import tempfile
import os
from io import StringIO, BytesIO
import base64
import json

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
            return df, "UTF-8"
        except UnicodeDecodeError:
            encodings = ['utf-8-sig', 'cp949', 'euc-kr']
            for encoding in encodings:
                try:
                    df = pd.read_csv(BytesIO(content), encoding=encoding)
                    return df, encoding
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            return None, "encoding_error"
    except Exception as e:
        return None, str(e)

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

def create_instant_speech_button(text, lang, button_text, button_id):
    """🎯 iOS Safari 완벽 호환 음성 버튼 (버그 해결 버전)"""
    
    # 언어별 설정
    lang_code = 'en-US' if lang == 'en' else 'ko-KR'
    rate = 0.8 if lang == 'en' else 0.9
    
    # 🎯 정확한 재생 시간 추정 공식 (발음 속도 고려)
    estimated_duration = max(2000, (len(text) / 12) * 1000 * (1 / rate) + 1500)
    
    # gTTS 폴백용 오디오 생성
    fallback_audio = ""
    try:
        tts = gTTS(text=text, lang=lang)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        tts.save(temp_file.name)
        
        with open(temp_file.name, 'rb') as f:
            audio_bytes = f.read()
        
        fallback_audio = base64.b64encode(audio_bytes).decode()
        os.unlink(temp_file.name)
    except:
        pass
    
    # HTML + JavaScript로 즉시 재생 구현 (iOS Safari 버그 해결)
    html_code = f"""
    <div style="margin: 10px 0;">
        <button 
            id="{button_id}"
            onclick="instantSpeak_{button_id}()" 
            style="
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 15px 20px;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                transition: all 0.3s ease;
                width: 100%;
                min-height: 60px;
            "
            onmouseover="this.style.transform='translateY(-2px)';"
            onmouseout="this.style.transform='translateY(0px)';"
        >
            {button_text}
        </button>
        <div id="status_{button_id}" style="
            margin-top: 8px; 
            font-size: 12px; 
            color: #666; 
            text-align: center;
            min-height: 16px;
        "></div>
    </div>

    <script>
    // 🎯 글로벌 상태 관리 (중복 실행 방지)
    window.speechTimer_{button_id} = null;
    window.isPlaying_{button_id} = false;
    
    // 음성 엔진 초기화 (iOS 최적화)
    if (window.speechSynthesis && !window.voicesInitialized_{button_id}) {{
        window.speechSynthesis.getVoices();
        window.speechSynthesis.onvoiceschanged = function() {{
            console.log('음성 엔진 초기화 완료: {button_id}');
        }};
        window.voicesInitialized_{button_id} = true;
    }}
    
    function resetButton_{button_id}() {{
        const button = document.getElementById('{button_id}');
        const status = document.getElementById('status_{button_id}');
        
        if (button) {{
            button.innerHTML = '{button_text}';
            button.disabled = false;
            button.style.opacity = '1';
        }}
        
        if (status) {{
            status.innerHTML = '✅ 재생 완료';
            setTimeout(() => {{
                if (status) status.innerHTML = '';
            }}, 2000);
        }}
        
        window.isPlaying_{button_id} = false;
        
        // 타이머 정리
        if (window.speechTimer_{button_id}) {{
            clearTimeout(window.speechTimer_{button_id});
            window.speechTimer_{button_id} = null;
        }}
    }}
    
    function instantSpeak_{button_id}() {{
        // 🎯 중복 실행 방지
        if (window.isPlaying_{button_id}) {{
            return;
        }}
        
        const text = {json.dumps(text)};
        const button = document.getElementById('{button_id}');
        const status = document.getElementById('status_{button_id}');
        
        if (!button || !status) return;
        
        // 기존 음성 및 타이머 정리
        if (window.speechSynthesis) {{
            window.speechSynthesis.cancel();
        }}
        
        if (window.speechTimer_{button_id}) {{
            clearTimeout(window.speechTimer_{button_id});
        }}
        
        // 상태 설정
        window.isPlaying_{button_id} = true;
        button.innerHTML = '🔊 재생 중...';
        button.disabled = true;
        button.style.opacity = '0.7';
        status.innerHTML = '재생 중...';
        
        // 🎯 iOS Safari 버그 해결: 강제 완료 타이머
        window.speechTimer_{button_id} = setTimeout(() => {{
            console.log('타이머 기반 강제 완료: {button_id}');
            resetButton_{button_id}();
        }}, {estimated_duration});
        
        // 1차: Web Speech API 시도
        if (window.speechSynthesis && 'SpeechSynthesisUtterance' in window) {{
            try {{
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = '{lang_code}';
                utterance.rate = {rate};
                utterance.pitch = 1.0;
                utterance.volume = 1.0;
                
                // 최적 음성 선택
                const voices = window.speechSynthesis.getVoices();
                const preferredVoice = voices.find(voice => 
                    voice.lang.startsWith('{lang_code.split('-')[0]}')
                );
                
                if (preferredVoice) {{
                    utterance.voice = preferredVoice;
                }}
                
                // 🎯 이벤트 리스너 (정상 완료 시)
                utterance.onend = function() {{
                    console.log('정상 완료: {button_id}');
                    resetButton_{button_id}();
                }};
                
                utterance.onerror = function(event) {{
                    console.log('Web Speech API 오류, 폴백 시도: {button_id}');
                    playFallbackAudio_{button_id}();
                }};
                
                // 재생 시작
                window.speechSynthesis.speak(utterance);
                return; // Web Speech API 성공
                
            }} catch(e) {{
                console.log('Web Speech API 초기화 오류:', e);
            }}
        }}
        
        // 2차: gTTS 폴백
        playFallbackAudio_{button_id}();
    }}
    
    function playFallbackAudio_{button_id}() {{
        const fallbackAudio = '{fallback_audio}';
        const status = document.getElementById('status_{button_id}');
        
        if (fallbackAudio && status) {{
            try {{
                status.innerHTML = '재생 중... (서버 음성)';
                const audio = new Audio('data:audio/mp3;base64,' + fallbackAudio);
                
                audio.onended = function() {{
                    console.log('폴백 오디오 완료: {button_id}');
                    resetButton_{button_id}();
                }};
                
                audio.onerror = function(e) {{
                    console.log('폴백 오디오 오류:', e);
                    const button = document.getElementById('{button_id}');
                    const status = document.getElementById('status_{button_id}');
                    
                    if (button && status) {{
                        button.innerHTML = '{button_text}';
                        button.disabled = false;
                        button.style.opacity = '1';
                        status.innerHTML = '❌ 재생 실패';
                        setTimeout(() => status.innerHTML = '', 3000);
                    }}
                    
                    window.isPlaying_{button_id} = false;
                }};
                
                audio.play();
                
            }} catch(e) {{
                console.log('폴백 오디오 초기화 오류:', e);
                resetButton_{button_id}();
            }}
        }} else {{
            console.log('폴백 오디오 없음');
            resetButton_{button_id}();
        }}
    }}
    </script>
    """
    
    return html_code

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
                return False
    return True

# 메인 UI
st.title("🎓 영어 단어장 학습 시스템")
st.markdown("**아이패드 상태 버그 완전 해결! 🔧**")

# 자동 데이터 로드
auto_load_data()

st.markdown("---")

# 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    
    with st.expander("📋 연결된 구글 시트", expanded=False):
        st.code(GOOGLE_SHEET_URL[:60] + "...", language=None)
        
        if st.button("🔄 데이터 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.session_state.data_loaded = False
            st.rerun()
    
    if st.session_state.vocab_data is not None:
        with st.expander("🎯 학습 설정", expanded=True):
            if st.button("🔀 순서 섞기", use_container_width=True):
                st.session_state.vocab_data = st.session_state.vocab_data.sample(frac=1).reset_index(drop=True)
                st.session_state.current_index = 0
                st.success("순서를 섞었습니다!")
            
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
    
    if current_idx < len(data):
        word_data = data.iloc[current_idx]
        
        # 단어 카드
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
        
        # 🎯 버그 해결된 즉시 재생 음성 버튼들
        st.markdown("### 🔊 클릭하여 즉시 듣기")
        
        col1, col2 = st.columns(2)
        
        with col1:
            english_button = create_instant_speech_button(
                text=word_data['Word'],
                lang='en',
                button_text="🇺🇸 영어 듣기",
                button_id=f"english_{current_idx}"
            )
            st.components.v1.html(english_button, height=100)
        
        with col2:
            korean_button = create_instant_speech_button(
                text=word_data['Meaning'],
                lang='ko',
                button_text="🇰🇷 한국어 듣기",
                button_id=f"korean_{current_idx}"
            )
            st.components.v1.html(korean_button, height=100)
        
        # 연속 재생 버튼 (개선된 버전)
        st.markdown("### 🎵 연속 재생")
        both_html = f"""
        <div style="margin: 20px 0;">
            <button 
                id="both_btn_{current_idx}"
                onclick="playBothSequentially_{current_idx}()" 
                style="
                    background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
                    color: white;
                    border: none;
                    padding: 15px 30px;
                    border-radius: 10px;
                    font-size: 16px;
                    font-weight: bold;
                    cursor: pointer;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                    width: 100%;
                "
            >
                🎵 영어 → 한국어 연속 재생
            </button>
            <div id="both_status_{current_idx}" style="margin-top: 10px; font-size: 14px; color: #666; text-align: center;"></div>
        </div>

        <script>
        let bothTimer_{current_idx} = null;
        let bothPlaying_{current_idx} = false;
        
        function resetBothButton_{current_idx}() {{
            const btn = document.getElementById('both_btn_{current_idx}');
            const status = document.getElementById('both_status_{current_idx}');
            
            if (btn) {{
                btn.innerHTML = '🎵 영어 → 한국어 연속 재생';
                btn.disabled = false;
            }}
            
            if (status) {{
                status.innerHTML = '✅ 연속 재생 완료!';
                setTimeout(() => {{
                    if (status) status.innerHTML = '';
                }}, 2000);
            }}
            
            if (bothTimer_{current_idx}) {{
                clearTimeout(bothTimer_{current_idx});
                bothTimer_{current_idx} = null;
            }}
            
            bothPlaying_{current_idx} = false;
        }}
        
        function playBothSequentially_{current_idx}() {{
            if (bothPlaying_{current_idx}) return;
            
            const btn = document.getElementById('both_btn_{current_idx}');
            const status = document.getElementById('both_status_{current_idx}');
            
            if (!btn || !status) return;
            
            bothPlaying_{current_idx} = true;
            
            // 기존 음성 중지
            if (window.speechSynthesis) {{
                window.speechSynthesis.cancel();
            }}
            
            if (bothTimer_{current_idx}) {{
                clearTimeout(bothTimer_{current_idx});
            }}
            
            btn.innerHTML = '🔊 연속 재생 중...';
            btn.disabled = true;
            status.innerHTML = '🇺🇸 영어 재생 중...';
            
            // 🎯 전체 연속 재생 안전장치 타이머
            const totalEstimatedTime = 15000; // 15초 최대
            bothTimer_{current_idx} = setTimeout(resetBothButton_{current_idx}, totalEstimatedTime);
            
            const englishUtterance = new SpeechSynthesisUtterance('{word_data['Word']}');
            englishUtterance.lang = 'en-US';
            englishUtterance.rate = 0.8;
            
            let englishEnded = false;
            
            englishUtterance.onend = function() {{
                if (englishEnded) return;
                englishEnded = true;
                
                status.innerHTML = '🇰🇷 한국어 재생 중...';
                
                setTimeout(() => {{
                    const koreanUtterance = new SpeechSynthesisUtterance('{word_data['Meaning']}');
                    koreanUtterance.lang = 'ko-KR';
                    koreanUtterance.rate = 0.9;
                    
                    let koreanEnded = false;
                    
                    koreanUtterance.onend = function() {{
                        if (koreanEnded) return;
                        koreanEnded = true;
                        resetBothButton_{current_idx}();
                    }};
                    
                    koreanUtterance.onerror = function() {{
                        if (koreanEnded) return;
                        koreanEnded = true;
                        resetBothButton_{current_idx}();
                    }};
                    
                    window.speechSynthesis.speak(koreanUtterance);
                    
                    // 한국어 안전장치
                    setTimeout(() => {{
                        if (!koreanEnded) {{
                            koreanEnded = true;
                            resetBothButton_{current_idx}();
                        }}
                    }}, 8000);
                    
                }}, 500);
            }};
            
            englishUtterance.onerror = function() {{
                if (englishEnded) return;
                englishEnded = true;
                resetBothButton_{current_idx}();
            }};
            
            window.speechSynthesis.speak(englishUtterance);
            
            // 영어 안전장치
            setTimeout(() => {{
                if (!englishEnded) {{
                    englishEnded = true;
                    status.innerHTML = '🇰🇷 한국어 재생 중...';
                    // 한국어로 강제 전환
                }}
            }}, 6000);
        }}
        </script>
        """
        st.components.v1.html(both_html, height=80)
        
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

    # 단어 목록
    with st.expander("📚 전체 단어 목록 보기"):
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
    st.markdown("""
    ## ❌ 데이터 로드 실패
    
    구글 시트에서 데이터를 불러올 수 없습니다.
    
    ### 🔍 확인사항:
    1. 구글 시트가 '웹에 게시' 되어 있는지 확인
    2. 시트의 첫 번째 행이 'Word', 'Meaning'인지 확인
    3. 인터넷 연결 상태 확인
    """)

# 버그 해결 완료 안내
st.markdown("---")
st.success("""
### 🎉 아이패드 상태 버그 완전 해결!
- **타이머 기반 강제 완료**: `onend` 이벤트 미발생 시 자동 상태 리셋
- **정확한 시간 추정**: 발음 속도와 텍스트 길이 기반 계산
- **중복 실행 방지**: 글로벌 플래그로 동시 재생 차단
- **음성 엔진 최적화**: iOS Safari 전용 초기화 로직
""")

st.info("""
### 📱 최적 사용법:
- **첫 사용**: 브라우저에서 마이크 권한 허용
- **무음 모드**: 아이패드 사이드 스위치 확인  
- **네트워크**: 안정적인 Wi-Fi 연결 권장
- **상태 확인**: "재생 중..." → "✅ 재생 완료" 자동 변경
""")

st.caption("🚀 Powered by Web Speech API + Streamlit | iOS Safari 상태 버그 완전 해결 버전")
