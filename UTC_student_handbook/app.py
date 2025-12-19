# -*- coding: utf-8 -*-
import time
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from langchain.vectorstores import Chroma
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.embeddings import HuggingFaceEmbeddings
from langchain_core.runnables import RunnablePassthrough, RunnableLambda, RunnableParallel
from langchain_core.output_parsers import StrOutputParser
import os
from dotenv import load_dotenv
from functools import wraps # Thêm để tạo decorator
import traceback # Thêm để in lỗi chi tiết

# --- Thêm các thư viện mới cho việc tìm kiếm ảnh ---
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor
import numpy as np
import pickle
import base64
import io

# --- Thêm thư viện cho việc upload PDF và RAG mới ---
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from datetime import date
import shutil # Để xử lý file/thư mục
from werkzeug.utils import secure_filename # Thêm import này

# ==========================================================
# PHẦN 1: CẤU HÌNH VÀ BIẾN MÔI TRƯỜNG
# ==========================================================
print("--- KHỞI ĐỘNG ỨNG DỤNG TRỢ LÝ SINH VIÊN ---")
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# Lấy thông tin admin và secret key từ .env
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password123")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "a_very_secret_key_for_sessions_12345")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY chưa được thiết lập trong .env")
if FLASK_SECRET_KEY == "a_very_secret_key_for_sessions_12345":
    print("⚠️ CẢNH BÁO: FLASK_SECRET_KEY đang dùng giá trị mặc định. Hãy đặt giá trị này trong .env")

# --- Cấu hình các đường dẫn toàn cục ---
PERSIST_DIRECTORY = "/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/soTaySinhVien_v2_bkai3"
IMAGE_EMBEDDING_FILE = '/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/ImageEmbeddings/page_embeddings.npy'
IMAGE_PAGE_LIST_FILE = '/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/ImageEmbeddings/page_list.pkl'
TEMPLATE_FOLDER_PATH = "/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/templates"
STATIC_FOLDER_PATH = "/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/static"
UPLOAD_FOLDER = "/tmp/utc_pdf_uploads" 
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 

# --- Khởi tạo các biến toàn cục ---
app = Flask(__name__,
             template_folder=TEMPLATE_FOLDER_PATH,
             static_folder=STATIC_FOLDER_PATH) # Thêm static_folder
app.config['SECRET_KEY'] = FLASK_SECRET_KEY # Cấu hình secret key cho session
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

chain_is_ready = False
image_search_is_ready = False
# ... (Các biến toàn cục khác) ...

# ===================================================================
# --- KHỐI 1: KHỞI TẠO CÁC THÀNH PHẦN LANGCHAIN (RAG VỚI RERANK) ---
# ===================================================================
try:
    print("🧠 [1/3] Đang khởi tạo hệ thống hỏi đáp văn bản (LangChain)...")
    embedding_fn = HuggingFaceEmbeddings(model_name="bkai-foundation-models/vietnamese-bi-encoder")
    vectorstore = Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embedding_fn)
    char_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 50})

    def rerank_by_date(docs):
        sorted_docs = sorted(docs, key=lambda doc: date.fromisoformat(doc.metadata.get('date', '1970-01-01')), reverse=True)
        return sorted_docs[:15]

    def format_docs(docs):
        formatted_chunks = []
        for doc in docs:
            # Lấy ngày và tên file từ metadata
            date_str = doc.metadata.get('date', 'Không rõ ngày')
            source = os.path.basename(doc.metadata.get('source', 'Không rõ nguồn'))
            
            # Tạo định dạng rõ ràng để AI đọc được
            # Ví dụ: [VĂN BẢN NGÀY: 2024-12-01] Nội dung...
            chunk_content = f"--- [TÀI LIỆU NGÀY: {date_str}] [NGUỒN: {source}] ---\n{doc.page_content}"
            formatted_chunks.append(chunk_content)
        
        return "\n\n".join(formatted_chunks)

    chat = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        convert_system_message_to_human=True,
        google_api_key=GOOGLE_API_KEY,
        temperature=0.1
    )

    # --- CẬP NHẬT TEMPLATE ĐỂ NHẬN LỊCH SỬ CHAT ---
    TEMPLATE = '''Bạn là một trợ lý ảo thân thiện và chuyên nghiệp của Trường Đại học Giao thông Vận tải (UTC).
    Nhiệm vụ của bạn là trả lời câu hỏi của sinh viên một cách chính xác và rõ ràng.
    Sử dụng các thông tin sau:
    1. Lịch sử trò chuyện trước đó (dùng để tham khảo nếu câu hỏi mới liên quan).
    2. Ngữ cảnh mới (dùng để trả lời câu hỏi mới).
    3. TUYỆT ĐỐI KHÔNG được gộp thông tin cũ và mới. Hãy coi thông tin cũ là đã hết hiệu lực.

    **Lịch sử trò chuyện:**
    {chat_history}
    
    **Ngữ cảnh mới (từ tài liệu):**
    ----------------
    {context}
    ----------------

    **Câu hỏi mới của sinh viên:**
    {question}

    **Hướng dẫn trả lời:**
    - Dựa vào lịch sử và ngữ cảnh mới để trả lời câu hỏi mới.
    - Nếu ngữ cảnh mới không chứa thông tin, hãy nói: "Rất tiếc, tôi không tìm thấy thông tin về vấn đề này trong Sổ tay sinh viên hoặc các tài liệu được cung cấp."
    - Giữ giọng văn chuyên nghiệp nhưng thân thiện.
    
    TRẢ LỜI:'''
    prompt_template = PromptTemplate.from_template(TEMPLATE)

    # --- CẬP NHẬT CHAIN ĐỂ NHẬN DICTIONARY VÀ TRẢ VỀ SOURCES ---
    # Chain này nhận input là: {"question": str, "chat_history": str}
    
    retrieval_and_rerank = RunnableParallel(
        question=lambda x: x['question'],
        chat_history=lambda x: x['chat_history'],
        retrieved_docs=(
            (lambda x: x['question']) # Lấy 'question' từ input
            | retriever 
            | RunnableLambda(rerank_by_date)
        )
    )
    
    setup_and_retrieval = RunnableParallel(
        context=lambda x: format_docs(x["retrieved_docs"]),
        question=lambda x: x["question"],
        chat_history=lambda x: x["chat_history"], # Chuyển chat_history sang bước tiếp theo
        sources=lambda x: x["retrieved_docs"]
    )
    
    answer_generation = RunnableParallel(
        answer=(
            prompt_template # Đã chứa cả 3 biến (context, question, chat_history)
            | chat 
            | StrOutputParser()
        ),
        sources=lambda x: x["sources"]
    )
    
    chain = retrieval_and_rerank | setup_and_retrieval | answer_generation
    
    print("✅ Hệ thống RAG (với rerank và bộ nhớ chat) đã khởi tạo thành công.")
    chain_is_ready = True

except Exception as e:
    print(f"❌ Lỗi khi khởi tạo các thành phần LangChain: {e}")
    traceback.print_exc()
    chain_is_ready = False


# =================================================================
# --- KHỐI 2: KHỞI TẠO TÌM KIẾM HÌNH ẢNH (VINTERN-1B) ---
# =================================================================
# (Giữ nguyên khối code gốc của bạn, vì nó đã chạy)
try:
    print("🖼️  [2/3] Đang khởi tạo hệ thống tìm kiếm hình ảnh...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   -> Sử dụng thiết bị: {device}")

    # 1. Load Model và Processor
    model_name = "5CD-AI/Vintern-Embedding-1B"
    image_processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
    image_model = AutoModel.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    ).eval().to(device)

    # 2. Load pre-computed embeddings and page images
    if os.path.exists(IMAGE_EMBEDDING_FILE) and os.path.exists(IMAGE_PAGE_LIST_FILE):
        loaded_embeddings_np = np.load(IMAGE_EMBEDDING_FILE)
        with open(IMAGE_PAGE_LIST_FILE, 'rb') as f:
            page_list = pickle.load(f)

        # Chuẩn bị list embeddings cho hàm score_multi_vector
        image_embeddings_list_of_tensors = [torch.tensor(emb).to(device) for emb in loaded_embeddings_np]
        
        print(f"✅ Hệ thống tìm kiếm hình ảnh sẵn sàng. Đã tải {len(page_list)} trang.")
        image_search_is_ready = True
    else:
        print(f"⚠️ Error: Không tìm thấy '{IMAGE_EMBEDDING_FILE}' hoặc '{IMAGE_PAGE_LIST_FILE}'.")
        image_search_is_ready = False

except Exception as e:
    print(f"❌ Lỗi khi khởi tạo hệ thống tìm kiếm hình ảnh: {e}")
    traceback.print_exc()
    image_search_is_ready = False

# --- Hàm tiện ích tìm kiếm ảnh (Giữ nguyên logic của bạn) ---
def search_images(query, top_k=3):
    batch_queries = image_processor.process_queries([query])
    batch_queries["input_ids"] = batch_queries["input_ids"].to(device)
    batch_queries["attention_mask"] = batch_queries["attention_mask"].to(device).bfloat16()
    with torch.no_grad():
        query_embeddings = image_model(**batch_queries)
    
    scores = image_processor.score_multi_vector(query_embeddings, image_embeddings_list_of_tensors)[0]
    top_indices = scores.cpu().argsort(descending=True)[:top_k]
    
    results = []
    for idx_tensor in top_indices:
        idx = idx_tensor.item()
        score = scores[idx].item()
        image = page_list[idx]
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        results.append({
            "score": score,
            "page_number": idx + 1, # Trả về page_number (1-based)
            "image_base64": f"data:image/png;base64,{img_str}"
        })
    return results

# ==========================================================
# PHẦN 3: LOGIC XÁC THỰC ADMIN (MỚI)
# ==========================================================
print("🔐 [3/3] Đang thiết lập các route xác thực Admin...")
def admin_required(f):
    """Decorator để bảo vệ route, yêu cầu đăng nhập admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Bạn cần đăng nhập để truy cập chức năng này.', 'warning')
            return redirect(url_for('login')) # Chuyển hướng về trang login
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Trang đăng nhập cho Admin."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('home')) # Chuyển về trang chủ
        else:
            flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Đăng xuất Admin."""
    session.pop('admin_logged_in', None)
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('home'))
print("✅ Các route Admin đã sẵn sàng.")


# ==========================================================
# PHẦN 4: CÁC ENDPOINTS CỦA ỨNG DỤNG
# ==========================================================

def image_to_base64(pil_image):
    buffered = io.BytesIO()
    pil_image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

@app.route('/')
def home():
    """Render trang chủ, truyền trạng thái đăng nhập vào template."""
    return render_template('index_admin.html', admin_logged_in=session.get('admin_logged_in', False))

# --- HÀM TIỆN ÍCH CHO BỘ NHỚ CHAT ---
def format_chat_history_for_prompt(history_list):
    """Chuyển đổi list (q, a) thành string cho prompt."""
    if not history_list:
        return "Không có"
    formatted = []
    for q, a in history_list:
        formatted.append(f"Người dùng: {q}\nTrợ lý: {a}")
    return "\n\n".join(formatted)

# --- ROUTE HỎI ĐÁP (ĐÃ CẬP NHẬT VỚI BỘ NHỚ CHAT) ---
@app.route('/ask', methods=['POST'])
def ask():
    if not chain_is_ready: 
        return jsonify({'error': 'Hệ thống AI (văn bản) chưa sẵn sàng.'}), 503

    user_question = request.json.get('question')
    if not user_question: 
        return jsonify({'error': 'Vui lòng nhập câu hỏi.'}), 400

    try:
        # --- LOGIC BỘ NHỚ ĐỆM ---
        k_memory = 3 # Giữ 3 lượt hội thoại cuối
        history_list = session.get('chat_history', [])
        history_string = format_chat_history_for_prompt(history_list)
        
        # Invoke chain với input là dictionary
        result = chain.invoke({
            "question": user_question,
            "chat_history": history_string
        })
        
        answer = result.get("answer", "Không có câu trả lời.")
        sources = result.get("sources", [])

        # Cập nhật lịch sử mới và lưu lại vào session
        history_list.append((user_question, answer))
        session['chat_history'] = history_list[-k_memory:] # Chỉ giữ 3 lượt Q&A cuối
        # --- KẾT THÚC LOGIC BỘ NHỚ ĐỆM ---

        # In debug ra backend
        print(f"\n{'='*50}\n🎯 CÂU HỎI: {user_question}\n🤖 TRẢ LỜI: {answer}\n📚 NGUỒN:")
        formatted_sources_for_json = []
        if sources:
             for i, doc in enumerate(sources[:5]):
                metadata = doc.metadata
                doc_date = metadata.get('date', 'Không rõ')
                source_file = metadata.get('source', 'Không rõ')
                source_filename = os.path.basename(source_file) if source_file != 'Không rõ' else 'Không rõ'
                page_num = metadata.get('page', None)
                display_page = page_num + 1 if isinstance(page_num, int) else 'N/A'
                content_preview = ' '.join(doc.page_content.split()[:20])
                print(f"   [{i+1}] Ngày: {doc_date} | Nguồn: {source_filename} | Trang: {display_page}")
                formatted_sources_for_json.append({
                    "date": doc_date, "filename": source_filename, "page": display_page,
                    "content_preview": content_preview
                })
        print(f"{'='*50}\n")
        
        return jsonify({
            'answer': answer
            # 'sources': formatted_sources_for_json 
        })

    except Exception as e:
        print(f"❌ Lỗi khi xử lý câu hỏi: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Đã có lỗi xảy ra trong quá trình xử lý câu hỏi của bạn.'}), 500

# --- ROUTE TÌM KIẾM HÌNH ẢNH (KHÔNG ĐỔI) ---
@app.route('/search_image', methods=['POST'])
def handle_search_image():
    if not image_search_is_ready:
        return jsonify({'error': 'Hệ thống tìm kiếm ảnh chưa sẵn sàng.'}), 503

    user_query = request.json.get('query')
    if not user_query:
        return jsonify({'error': 'Vui lòng nhập nội dung tìm kiếm.'}), 400
    
    try:
        search_results = search_images(user_query, top_k=2) # Tìm kiếm top 2 ảnh
        return jsonify({'results': search_results})
    
    except Exception as e:
        print(f"❌ Lỗi khi tìm kiếm ảnh: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Đã có lỗi xảy ra trong quá trình tìm kiếm hình ảnh.'}), 500

# --- ROUTE UPLOAD PDF (ĐÃ ĐƯỢC BẢO VỆ VÀ CẬP NHẬT) ---
@app.route('/upload_pdf', methods=['POST'])
@admin_required # <-- Chỉ admin mới được truy cập
def handle_upload_pdf():
    # Kiểm tra file và ngày tháng từ form
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'Không tìm thấy file (key=pdf_file).'}), 400
    if 'document_date' not in request.form:
         return jsonify({'error': 'Không tìm thấy ngày (key=document_date).'}), 400
         
    file = request.files['pdf_file']
    document_date_str = request.form['document_date']
    
    if file.filename == '':
        return jsonify({'error': 'Không có file nào được chọn.'}), 400
    if not document_date_str:
        return jsonify({'error': 'Vui lòng chọn ngày cho văn bản.'}), 400
        
    if file and file.filename.lower().endswith('.pdf'):
        filepath = "" # Khởi tạo để dùng trong finally
        try:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            print(f"\n--- ADMIN: BẮT ĐẦU BỔ SUNG DỮ LIỆU MỚI ---")
            print(f"📄 Đang xử lý file: {filepath}")

            loader_pdf = PyPDFLoader(filepath)
            pages_pdf = loader_pdf.load()

            # Sử dụng char_splitter đã khởi tạo toàn cục
            pdf_char_split = char_splitter.split_documents(pages_pdf)

            # Gắn tem thời gian từ form
            upload_date = date.fromisoformat(document_date_str).isoformat()
            print(f"🏷️  Đang gắn tem thời gian '{upload_date}' cho {len(pdf_char_split)} chunks...")
            
            for doc in pdf_char_split:
                # Ghi đè hoặc thêm date, giữ lại source gốc từ PyPDFLoader
                doc.metadata = {**doc.metadata, "date": upload_date} 

            if pdf_char_split:
                # Sử dụng vectorstore toàn cục
                vectorstore.add_documents(pdf_char_split)
                count = vectorstore._collection.count()
                print(f"✅ Đã thêm thành công {len(pdf_char_split)} đoạn văn bản mới.")
                print(f"   -> Tổng số tài liệu hiện tại: {count}")
            
            return jsonify({
                'message': f'Đã xử lý thành công file: {filename}',
                'chunks_added': len(pdf_char_split),
                'date_added': upload_date,
                'total_documents': count
            }), 200

        except Exception as e:
            print(f"❌ Lỗi khi xử lý file upload: {e}")
            traceback.print_exc()
            return jsonify({'error': f'Đã có lỗi xảy ra khi xử lý file: {e}'}), 500
        finally:
             # Dọn dẹp file tạm sau khi xử lý
            if os.path.exists(filepath):
                os.remove(filepath)
    else:
        return jsonify({'error': 'File không hợp lệ. Chỉ chấp nhận file .pdf'}), 400

# ===========================
# --- KHỐI 5: CHẠY APP ---
# ===========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)