import json
import re
import google.generativeai as genai
from fastapi import FastAPI, Body, HTTPException, UploadFile, File, Form
from databases import Database

# --- DATABASE CONFIGURATION ---
DATABASE_URL = "mysql+aiomysql://root:@localhost/uni_guide"
database = Database(DATABASE_URL)
app = FastAPI()

# --- AI CONFIGURATION ---
API_KEY = "AIzaSyClN__3CmDPcjx585jCnpE2Z8iAoeSuv5k" 
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

@app.on_event("startup")
async def startup():
    await database.connect()
    # Create tables safely
    await database.execute("""
        CREATE TABLE IF NOT EXISTS tutor_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            course_code VARCHAR(50),
            question TEXT,
            answer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await database.execute("""
        CREATE TABLE IF NOT EXISTS course_units (
            course_code VARCHAR(50) PRIMARY KEY,
            w_quiz FLOAT, w_midterm FLOAT, w_assignment FLOAT, w_final FLOAT
        )
    """)
    print("✅ UNI-GUIDE Master Backend is Online")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# --- SAFE JSON PARSER ---
def safe_parse_json(text: str) -> dict:
    """Aggressively cleans AI output to prevent JSON crashes."""
    try:
        cleaned = text.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(json)?|```$', '', cleaned, flags=re.MULTILINE).strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {} # Return empty dict instead of crashing

def safe_float(val) -> float:
    """Ensures values are saved as floats even if AI adds '%'."""
    try:
        return float(str(val).replace('%', '').strip())
    except:
        return 0.0

# --- A-Z FEATURE: AI TUTOR & MEMORY ---
@app.get("/get_history/{course_code}")
async def get_history(course_code: str):
    return await database.fetch_all(
        "SELECT question, answer FROM tutor_history WHERE course_code = :c ORDER BY id DESC", 
        {"c": course_code.upper().strip()}
    )

@app.post("/ask_tutor")
async def ask_tutor(data: dict = Body(...)):
    code = data.get("course_code", "GENERAL").upper().strip()
    q = data.get("question", "")
    
    # Contextual Memory (C)
    h = await database.fetch_all("SELECT question, answer FROM tutor_history WHERE course_code = :c ORDER BY id DESC LIMIT 5", {"c": code})
    ctx = "\n".join([f"User: {r['question']}\nAI: {r['answer']}" for r in reversed(h)])
    
    # Strict prompt for Bilingual output (A)
    prompt = f"""
    You are an expert academic mentor for {code}. 
    Previous Context: {ctx}. 
    Respond to the query strictly in this JSON format ONLY:
    {{"title": "Topic", "explanation_en": "English answer", "explanation_si": "Sinhala answer", "summary": "Short summary"}}
    """
    
    resp = model.generate_content([prompt, f"Query: {q}"], generation_config={"response_mime_type": "application/json"})
    res_data = safe_parse_json(resp.text)
    
    # Save to history (H)
    ans_text = res_data.get('explanation_en', 'No explanation provided.')
    await database.execute("INSERT INTO tutor_history (course_code, question, answer) VALUES (:c, :q, :a)", 
                           {"c": code, "q": q, "a": ans_text})
    
    return res_data

# --- A-Z FEATURE: PDF STUDY MODE (P) ---
@app.post("/tutor_upload")
async def tutor_upload(course_code: str = Form(...), question: str = Form(...), file: UploadFile = File(...)):
    code = course_code.upper().strip()
    content = await file.read()
    prompt = f"Analyze this PDF for {code}. JSON format strictly: {{\"title\": \"Insight\", \"explanation_en\": \"English text\", \"explanation_si\": \"Sinhala text\", \"summary\": \"Summary\"}}"
    
    resp = model.generate_content([prompt, {"mime_type": "application/pdf", "data": content}, f"Query: {question}"], 
                                  generation_config={"response_mime_type": "application/json"})
    res_data = safe_parse_json(resp.text)
    
    ans_text = res_data.get('explanation_en', 'No explanation provided.')
    await database.execute("INSERT INTO tutor_history (course_code, question, answer) VALUES (:c, :q, :a)", 
                           {"c": code, "q": f"PDF({file.filename}): {question}", "a": ans_text})
    return res_data

# --- A-Z FEATURE: GPA ENGINE (G & E) ---
@app.get("/check_rules/{course_code}")
async def check_rules(course_code: str):
    res = await database.fetch_one("SELECT * FROM course_units WHERE course_code = :c", {"c": course_code.upper().strip()})
    return {"exists": res is not None, "rules": dict(res) if res else {}}

@app.post("/extract_rules/{course_code}")
async def extract_rules(course_code: str, file: UploadFile = File(...)):
    code = course_code.upper().strip()
    content = await file.read()
    prompt = 'Extract the percentage weights. ONLY output a valid JSON like: {"quiz": 10, "mid": 20, "asmt": 20, "final": 50}. Use 0 if missing.'
    
    resp = model.generate_content([prompt, {"mime_type": "application/pdf", "data": content}], 
                                  generation_config={"response_mime_type": "application/json"})
    w = safe_parse_json(resp.text)
    
    await database.execute(
        "REPLACE INTO course_units (course_code, w_quiz, w_midterm, w_assignment, w_final) VALUES (:c, :q, :m, :a, :f)", 
        {"c": code, "q": safe_float(w.get('quiz',0)), "m": safe_float(w.get('mid',0)), "a": safe_float(w.get('asmt',0)), "f": safe_float(w.get('final',0))}
    )
    return {"status": "success"}

@app.get("/calculate_gpa/{course_code}")
async def calculate_gpa(course_code: str, q1:float, q2:float, q3:float, mid:float, asmt:float, final:float, att:float):
    code = course_code.upper().strip()
    r = await database.fetch_one("SELECT * FROM course_units WHERE course_code=:c", {"c": code})
    if not r: 
        raise HTTPException(404, "Rules not found")
    
    # Best 2 of 3 quizzes
    quiz_avg = sum(sorted([q1, q2, q3], reverse=True)[:2]) / 2
    
    # Weighted calculation
    total = (quiz_avg * r['w_quiz']/100) + (mid * r['w_midterm']/100) + (asmt * r['w_assignment']/100) + (final * r['w_final']/100)
    ca = total - (final * r['w_final']/100)
    
    # Eligibility rules
    is_eligible = (att >= 80) and (ca >= 15)
    gpa = (total / 100) * 4.0
    
    return {"gpa": round(gpa, 2), "total": round(total, 2), "ca": round(ca, 2), "eligible": is_eligible}