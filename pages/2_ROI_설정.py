# pages/2_ROI_설정.py — ROI(관심구역) 직접 그리기 화면
#
# 사용 흐름:
#   1. 영상 소스 선택 → 첫 프레임 불러오기
#   2. 영상 위에 마우스로 점을 클릭 → 자동으로 다각형 완성
#   3. 저장 버튼 클릭 → roi_configs/<이름>.json 저장
#   4. 모니터링 페이지에서 같은 이름으로 자동 로드

import streamlit as st
import cv2
import os
import sys
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import DATA_DIR
from core.video_source import VideoSource
from core.roi_manager  import save_roi, load_roi, draw_roi_on_frame, list_saved_rois

# streamlit-drawable-canvas 임포트 (없으면 안내 메시지)
try:
    from streamlit_drawable_canvas import st_canvas
    CANVAS_AVAILABLE = True
except ImportError:
    CANVAS_AVAILABLE = False

# ── 페이지 설정 ────────────────────────────────────────
st.set_page_config(
    page_title="ROI 설정 | 보행자 위험 감지",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ ROI(관심구역) 설정")

# 라이브러리 미설치 시 안내
if not CANVAS_AVAILABLE:
    st.error(
        "❌ `streamlit-drawable-canvas` 라이브러리가 없습니다.\n\n"
        "터미널에서 아래 명령어를 실행하고 앱을 재시작하세요:\n\n"
        "```\npip install streamlit-drawable-canvas\n```"
    )
    st.stop()

st.markdown("""
**사용 방법:** 영상 프레임 위에서 마우스로 **점을 클릭**하면 자동으로 위험 구역(다각형)이 만들어집니다.
완성 후 **💾 ROI 저장** 버튼을 누르세요.
""")
st.markdown("---")


# ══════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════
CANVAS_MAX_WIDTH = 800   # 캔버스 최대 표시 너비(픽셀)

def get_video_files() -> list:
    if not os.path.exists(DATA_DIR):
        return []
    return [
        f for f in os.listdir(DATA_DIR)
        if f.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))
    ]

def extract_polygon_from_canvas(json_data: dict, scale: float) -> np.ndarray | None:
    """
    st_canvas 결과 JSON에서 다각형 좌표를 추출합니다.
    캔버스 표시 크기에서 원본 프레임 크기로 역스케일합니다.
    """
    if not json_data:
        return None
    objects = json_data.get("objects", [])
    if not objects:
        return None

    # 가장 마지막으로 그린 다각형 사용
    for obj in reversed(objects):
        if obj.get("type") != "path":
            continue
        path = obj.get("path", [])
        points = []
        for cmd in path:
            # SVG path 명령어: M(시작점), L(직선), z(닫기)
            if cmd[0] in ("M", "L") and len(cmd) >= 3:
                x = int(round(cmd[1] / scale))
                y = int(round(cmd[2] / scale))
                points.append([x, y])
        if len(points) >= 3:
            return np.array(points, dtype=np.int32)

    return None


# ══════════════════════════════════════════════════════
# 레이아웃: 사이드바(설정) + 메인(캔버스)
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ 소스 설정")

    source_type = st.radio(
        "영상 소스",
        ["📁 로컬 영상 파일", "📡 RTSP 스트림"],
    )

    selected_source = None
    source_label    = ""

    if source_type == "📁 로컬 영상 파일":
        video_files = get_video_files()
        if video_files:
            chosen       = st.selectbox("파일 선택", video_files)
            selected_source = os.path.join(DATA_DIR, chosen)
            source_label    = os.path.splitext(chosen)[0]
        else:
            st.warning("`data/` 폴더에 영상 파일을 넣어주세요.")
    else:
        rtsp_url = st.text_input(
            "RTSP 주소",
            placeholder="rtsp://admin:1234@192.168.0.100:554/Streaming/Channels/402",
        )
        if rtsp_url.startswith("rtsp://"):
            selected_source = rtsp_url

    source_label = st.text_input(
        "ROI 저장 이름",
        value=source_label,
        help="모니터링 페이지에서 이 이름과 같은 소스를 선택해야 ROI가 자동 로드됩니다.",
    )

    st.markdown("---")

    # 기준 프레임 불러오기
    load_btn = st.button(
        "📷 기준 프레임 불러오기",
        type="primary",
        disabled=selected_source is None,
        use_container_width=True,
    )
    if load_btn:
        with st.spinner("프레임 로딩 중..."):
            vs    = VideoSource(selected_source)
            frame = vs.get_first_frame()
        if frame is not None:
            st.session_state["roi_frame"]       = frame
            st.session_state["roi_source_label"] = source_label
            st.session_state["roi_canvas_key"]  = st.session_state.get("roi_canvas_key", 0) + 1
            h, w = frame.shape[:2]
            st.success(f"✅ 프레임 로드 완료 ({w}×{h})")
        else:
            st.error("❌ 프레임을 가져올 수 없습니다. 소스를 확인하세요.")

    st.markdown("---")

    # 저장된 ROI 목록 & 불러오기
    st.subheader("📂 저장된 ROI")
    saved_list = list_saved_rois()
    if saved_list:
        sel = st.selectbox("불러올 ROI 선택", ["— 선택 —"] + saved_list)
        if sel != "— 선택 —":
            pts = load_roi(sel)
            if pts is not None:
                st.success(f"'{sel}': {len(pts)}개 꼭짓점")
                st.caption("\n".join(f"P{i+1}: ({p[0]}, {p[1]})" for i, p in enumerate(pts)))
    else:
        st.caption("저장된 ROI 없음")

    st.markdown("---")

    # 도움말
    with st.expander("❓ 사용 방법 안내"):
        st.markdown("""
        1. 영상 소스를 선택하고 **기준 프레임 불러오기** 클릭
        2. 오른쪽 영상 위에서 **마우스 클릭**으로 꼭짓점을 찍으세요
        3. 마지막 점에서 **더블클릭**하면 다각형이 닫힙니다
        4. 잘못 그렸으면 **🗑️ 다시 그리기** 버튼 클릭
        5. 완성 후 **💾 ROI 저장** 클릭
        ---
        💡 **좌표 (0,0)** = 화면 왼쪽 상단
        💡 꼭짓점은 **최소 3개** 이상이어야 합니다
        """)


# ══════════════════════════════════════════════════════
# 메인 영역: 캔버스
# ══════════════════════════════════════════════════════
frame = st.session_state.get("roi_frame", None)

if frame is None:
    st.info(
        "👈 왼쪽 사이드바에서 영상 소스를 선택한 뒤\n\n"
        "**📷 기준 프레임 불러오기** 버튼을 클릭하면\n\n"
        "여기에 영상이 표시됩니다."
    )
    st.stop()

# ── 프레임 크기 & 스케일 계산 ───────────────────────────
orig_h, orig_w = frame.shape[:2]
scale          = CANVAS_MAX_WIDTH / orig_w
canvas_w       = CANVAS_MAX_WIDTH
canvas_h       = int(orig_h * scale)

# ── BGR → PIL 변환 (캔버스 배경 이미지) ─────────────────
rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
pil_img = Image.fromarray(rgb).resize((canvas_w, canvas_h), Image.LANCZOS)

# ── 상단 버튼 행 ─────────────────────────────────────────
btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])

# 다시 그리기: canvas key를 바꿔서 캔버스를 초기화
if btn_col1.button("🗑️ 다시 그리기", use_container_width=True):
    st.session_state["roi_canvas_key"] = st.session_state.get("roi_canvas_key", 0) + 1
    st.rerun()

# ROI 저장 버튼
save_clicked = btn_col2.button("💾 ROI 저장", type="primary", use_container_width=True)

btn_col3.caption(
    f"원본 해상도: {orig_w}×{orig_h} | "
    f"캔버스: {canvas_w}×{canvas_h} | "
    f"저장 이름: **{st.session_state.get('roi_source_label', source_label) or '(미입력)'}**"
)

# ── 캔버스 표시 ──────────────────────────────────────────
st.markdown("##### ✏️ 영상 위에 마우스로 점을 클릭해 ROI를 그리세요")
st.caption("클릭 → 꼭짓점 추가 | 더블클릭 → 다각형 완성 | 🗑️ 버튼 → 초기화")

canvas_result = st_canvas(
    fill_color    = "rgba(0, 255, 200, 0.15)",   # ROI 내부 반투명 녹색
    stroke_width  = 2,
    stroke_color  = "#00FFC8",                    # ROI 테두리 색
    background_image = pil_img,
    drawing_mode  = "polygon",                    # 다각형 모드
    point_display_radius = 6,                     # 꼭짓점 점 크기
    key           = f"roi_canvas_{st.session_state.get('roi_canvas_key', 0)}",
    height        = canvas_h,
    width         = canvas_w,
    update_streamlit = True,
)

# ── 좌표 추출 & 미리보기 ─────────────────────────────────
roi_pts = extract_polygon_from_canvas(canvas_result.json_data, scale)

if roi_pts is not None:
    # 추출된 좌표 정보 표시
    info_col1, info_col2 = st.columns([1, 2])
    with info_col1:
        st.success(f"✅ {len(roi_pts)}개 꼭짓점 인식됨")
        pts_text = "\n".join(f"P{i+1}: ({p[0]}, {p[1]})" for i, p in enumerate(roi_pts))
        st.code(pts_text, language=None)
    with info_col2:
        # 원본 프레임에 ROI 오버레이해서 확인용으로 표시
        preview = frame.copy()
        preview = draw_roi_on_frame(preview, roi_pts, danger=False)
        for i, pt in enumerate(roi_pts):
            cv2.putText(
                preview, f"P{i+1}",
                (int(pt[0]) + 5, int(pt[1]) - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 255, 200), 2, cv2.LINE_AA,
            )
        preview_rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        st.image(
            Image.fromarray(preview_rgb).resize((canvas_w, canvas_h), Image.LANCZOS),
            caption="원본 해상도 기준 ROI 미리보기",
            use_container_width=True,
        )
else:
    if canvas_result.json_data and canvas_result.json_data.get("objects"):
        st.warning("⚠️ 다각형을 완성하려면 마지막 점에서 **더블클릭**하세요.")
    else:
        st.info("👆 위 영상 위에서 마우스로 점을 클릭해 ROI를 그려보세요.")

# ── 저장 처리 ────────────────────────────────────────────
if save_clicked:
    label_to_save = st.session_state.get("roi_source_label", source_label) or source_label
    if not label_to_save:
        st.error("❌ 사이드바에서 **ROI 저장 이름**을 입력하세요.")
    elif roi_pts is None:
        st.error("❌ 저장할 ROI가 없습니다. 영상 위에 다각형을 먼저 그려주세요.")
    elif len(roi_pts) < 3:
        st.error("❌ 꼭짓점이 3개 이상이어야 합니다.")
    else:
        path = save_roi(label_to_save, roi_pts.tolist())
        st.success(
            f"✅ ROI 저장 완료!\n\n"
            f"- 이름: **{label_to_save}**\n"
            f"- 꼭짓점: {len(roi_pts)}개\n"
            f"- 저장 경로: `{path}`\n\n"
            f"모니터링 페이지에서 **{label_to_save}** 소스를 선택하면 자동 로드됩니다."
        )
