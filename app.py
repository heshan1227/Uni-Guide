import streamlit as st
import requests

API_URL = "http://localhost:8000"
st.set_page_config(page_title="UNI-GUIDE Master", layout="wide", page_icon="🎓")

# Sidebar
st.sidebar.title("🎓 UNI-GUIDE")
topic = st.sidebar.text_input("Course Code:", "1152").upper().strip()

# Smart Topic Change Detection to clear old GPA results
if 'current_topic' not in st.session_state or st.session_state.current_topic != topic:
    st.session_state.current_topic = topic
    if 'res' in st.session_state:
        del st.session_state['res']

nav = st.sidebar.radio("Menu", ["1. AI Tutor", "2. GPA Engine"])

# --- PAGE 1: AI TUTOR ---
if nav == "1. AI Tutor":
    st.header(f"🤖 Academic Mentor: {topic}")
    m = st.tabs(["💬 Quick Chat", "📑 PDF Study"])
    
    with m[0]:
        q = st.chat_input("Ask a question...")
        if q:
            with st.spinner("Thinking..."):
                res = requests.post(f"{API_URL}/ask_tutor", json={"course_code": topic, "question": q})
                if res.status_code == 200:
                    d = res.json()
                    st.subheader(d.get('title', 'Explanation'))
                    c1, c2 = st.columns(2)
                    # The absolute fix for the KeyError: using .get() with fallbacks
                    c1.info(f"**English:**\n\n{d.get('explanation_en', 'Data could not be parsed.')}")
                    c2.success(f"**සිංහල:**\n\n{d.get('explanation_si', 'Data could not be parsed.')}")
                    st.caption(d.get('summary', ''))
                else:
                    st.error("Server Error. Please try again.")

    with m[1]:
        f = st.file_uploader("Upload Notes (PDF)", type=['pdf'])
        pq = st.text_input("What do you want to find?")
        if st.button("Analyze PDF") and f and pq:
            with st.spinner("Reading Document..."):
                res = requests.post(f"{API_URL}/tutor_upload", files={"file": f}, data={"course_code":topic, "question":pq})
                if res.status_code == 200:
                    d = res.json()
                    st.subheader(d.get('title', 'PDF Insight'))
                    c1, c2 = st.columns(2)
                    c1.info(f"**English:**\n\n{d.get('explanation_en', 'Error.')}")
                    c2.success(f"**සිංහල:**\n\n{d.get('explanation_si', 'Error.')}")

    st.divider()
    st.subheader("📚 Saved Knowledge (phpMyAdmin)")
    try:
        hist = requests.get(f"{API_URL}/get_history/{topic}").json()
        if hist:
            for h in hist:
                with st.expander(f"Q: {h['question']}"): 
                    st.write(h['answer'])
        else:
            st.write("No history saved yet.")
    except Exception:
        st.write("Could not load history.")

# --- PAGE 2: GPA ENGINE ---
elif nav == "2. GPA Engine":
    st.header(f"📊 GPA & Eligibility Engine: {topic}")
    
    # PROOF SYSTEM: Visually confirm if rules exist
    rules_check = requests.get(f"{API_URL}/check_rules/{topic}").json()
    
    if rules_check['exists']:
        r = rules_check['rules']
        st.success(f"✅ Rules Loaded for {topic} — Quiz: {r['w_quiz']}%, Mid: {r['w_midterm']}%, Asmt: {r['w_assignment']}%, Final: {r['w_final']}%")
    else:
        st.warning(f"⚠️ Action Required: Upload {topic} syllabus in Step 1 to extract rules.")

    c1, c2 = st.columns(2, gap="large")

    with c1:
        st.subheader("🛠️ Step 1: Save Rules")
        sf = st.file_uploader("Syllabus PDF", type=['pdf'], key="s_pdf")
        if st.button("Save Assessment Rules"):
            if sf:
                with st.spinner("AI is extracting weights..."):
                    res = requests.post(f"{API_URL}/extract_rules/{topic}", files={"file": sf})
                    if res.status_code == 200: 
                        st.success("Rules Saved! Refreshing...")
                        st.rerun()  # Instantly reloads to show the green banner
                    else:
                        st.error("Failed to parse PDF weights.")
            else:
                st.error("Please upload a file.")

    with c2:
        st.subheader("📝 Step 2: Final Marks")
        marks = {
            "q1": st.number_input("Quiz 1", 0, 100), "q2": st.number_input("Quiz 2", 0, 100), "q3": st.number_input("Quiz 3", 0, 100),
            "mid": st.number_input("Mid-term", 0, 100), "asmt": st.number_input("Assignment", 0, 100),
            "final": st.number_input("Final Exam", 0, 100), "att": st.number_input("Attendance %", 0, 100, 80)
        }
        
        # Disable button if rules don't exist
        btn_disabled = not rules_check['exists']
        if st.button("🚀 Calculate Final Result", disabled=btn_disabled):
            res = requests.get(f"{API_URL}/calculate_gpa/{topic}", params=marks)
            if res.status_code == 200:
                st.session_state['res'] = res.json()
            else:
                st.error("Error: Could not calculate.")

        # FINAL DISPLAY (S - Session State persistence)
        if 'res' in st.session_state and rules_check['exists']:
            d = st.session_state['res']
            st.divider()
            st.balloons()
            st.metric(label="YOUR CALCULATED GPA", value=f"{d['gpa']} / 4.0")
            
            sc1, sc2 = st.columns(2)
            sc1.write(f"**Total Marks:** {d['total']}%")
            sc1.write(f"**CA Marks:** {d['ca']}")
            
            if d['eligible']: 
                sc2.success("ELIGIBILITY: PASSED ✅")
            else: 
                sc2.error("ELIGIBILITY: FAILED ❌")
            
            st.info("💡 Note: Formula takes Best 2 out of 3 quizzes. Eligibility requires ≥ 80% Attendance and ≥ 15 CA.")