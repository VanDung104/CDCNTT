import time
from flask import Flask, render_template, request, jsonify
from langchain.vectorstores import Chroma
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.embeddings import HuggingFaceEmbeddings
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
import os
from dotenv import load_dotenv

# --- Thêm các thư viện mới cho việc tìm kiếm ảnh ---
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor
import numpy as np
import pickle
import base64
import io

# Load biến môi trường từ file .env
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY chưa được thiết lập trong .env")


# --- Initialize Flask App ---
app = Flask(__name__,
             template_folder="/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/templates")

# ===================================================================
# --- KHỐI 1: KHỞI TẠO CÁC THÀNH PHẦN LANGCHAIN (TRẢ LỜI BẰNG VĂN BẢN) ---
# ===================================================================
try:
    # 1. Load vectorstore
    embedding_fn = HuggingFaceEmbeddings(
        model_name="bkai-foundation-models/vietnamese-bi-encoder"
    )
    vectorstore_from_directory = Chroma(
        persist_directory="/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/soTaySinhVien_v2_bkai",
        embedding_function=embedding_fn
    )

    # 2. LLM: Gemini
    chat = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", # Using a powerful and recent model
        temperature=0.1,
        convert_system_message_to_human=True,
    )

    # 3. Retriever
    retriever = vectorstore_from_directory.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 15, "lambda_mult": 0.9}
    )

    TEMPLATE = '''
    Bạn là một trợ lý ảo thân thiện và chuyên nghiệp của Trường Đại học Giao thông Vận tải (UTC).
    Nhiệm vụ của bạn là trả lời câu hỏi của sinh viên một cách chính xác và rõ ràng dựa trên Sổ tay sinh viên.

    **Chỉ sử dụng thông tin từ ngữ cảnh sau đây để trả lời:**
    ----------------
    {context}
    ----------------

    **Câu hỏi của sinh viên:**
    {question}

    **Hướng dẫn trả lời:**
    - Trả lời thẳng vào câu hỏi, không thêm thông tin ngoài lề.
    - Nếu ngữ cảnh không chứa thông tin để trả lời, hãy nói: "Rất tiếc, tôi không tìm thấy thông tin về vấn đề này trong Sổ tay sinh viên."
    - Giữ giọng văn chuyên nghiệp nhưng thân thiện.
    '''
    prompt_template = PromptTemplate.from_template(TEMPLATE)
    

    # 5. Create LangChain Chain
    def format_docs(docs):
        """Formats documents to be used in the prompt."""
        return "\n".join(doc.page_content for doc in docs)

    chain = (
        {
            'context': retriever | format_docs,
            'question': RunnablePassthrough()
        }
        | prompt_template
        | chat
        | StrOutputParser()
    )
    print("✅ LangChain components initialized successfully.")
    chain_is_ready = True
except Exception as e:
    print(f"❌ Error initializing LangChain components: {e}")
    chain_is_ready = False


# =================================================================
# --- KHỐI 2: KHỞI TẠO CÁC THÀNH PHẦN TÌM KIẾM HÌNH ẢNH (VINTERN) ---
# =================================================================
image_search_is_ready = False
try:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🔧 Using device for image search: {device}")

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
    embedding_file = '/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/ImageEmbeddings/page_embeddings.npy'
    page_list_file = '/mnt/d/Nam5ki1/CDCNTT/UTC_student_handbook/ImageEmbeddings/page_list.pkl'

    if os.path.exists(embedding_file) and os.path.exists(page_list_file):
        loaded_embeddings_np = np.load(embedding_file)
        with open(page_list_file, 'rb') as f:
            page_list = pickle.load(f)

        # Convert to tensor and normalize
        image_embeddings_tensor = torch.tensor(loaded_embeddings_np).to(device)
        image_embeddings_tensor = torch.nn.functional.normalize(image_embeddings_tensor.float(), p=2, dim=1)
        
        print(f"✅ Image search components initialized successfully. Loaded {len(page_list)} pages.")
        image_search_is_ready = True
    else:
        print(f"⚠️ Error: Could not find '{embedding_file}' or '{page_list_file}'. Image search will be unavailable.")

except Exception as e:
    print(f"❌ Error initializing Image Search components: {e}")
    image_search_is_ready = False


# --- Helper Function for Image Search ---
def search_images(query, top_k=3):
    """
    Searches for relevant images based on a text query and returns them as Base64 strings.
    """
    # Prepare batch query
    batch_queries = image_processor.process_queries([query])
    batch_queries["input_ids"] = batch_queries["input_ids"].to(device)
    batch_queries["attention_mask"] = batch_queries["attention_mask"].to(device).bfloat16()

    # Compute query embedding
    with torch.no_grad():
        query_embeddings = image_model(**batch_queries)

    # Calculate scores and get top indices
    scores = image_processor.score_multi_vector(query_embeddings, image_embeddings_tensor)[0]
    top_indices = scores.argsort(descending=True)[:top_k]

    results = []
    for idx_tensor in top_indices:
        idx = idx_tensor.item()
        score = scores[idx].item()
        image = page_list[idx]

        # Convert PIL Image to Base64 string
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        results.append({
            "score": score,
            "page_index": idx,
            "image_base64": f"data:image/png;base64,{img_str}"
        })
        
    return results

# ===========================
# ---   DEFINE FLASK ROUTES ---
# ===========================

@app.route('/')
def home():
    """Renders the main web page."""
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask():
    """Handles the API request for a question and returns a text answer."""
    if not chain_is_ready:
        return jsonify({'error': 'Hệ thống AI (văn bản) chưa sẵn sàng. Vui lòng kiểm tra lại cấu hình.'}), 503

    user_question = request.json.get('question')
    if not user_question:
        return jsonify({'error': 'Vui lòng nhập câu hỏi.'}), 400

    try:
        # Invoke the chain to get the answer
        answer = chain.invoke(user_question)
        return jsonify({'answer': answer})

    except Exception as e:
        print(f"Error during chain invocation: {e}")
        return jsonify({'error': 'Đã có lỗi xảy ra trong quá trình xử lý câu hỏi của bạn.'}), 500


@app.route('/search_image', methods=['POST'])
def handle_search_image():
    """Handles the API request for an image search and returns relevant page images."""
    if not image_search_is_ready:
        return jsonify({'error': 'Hệ thống tìm kiếm ảnh chưa sẵn sàng. Vui lòng kiểm tra lại cấu hình.'}), 503

    user_query = request.json.get('query')
    if not user_query:
        return jsonify({'error': 'Vui lòng nhập nội dung tìm kiếm.'}), 400
    
    try:
        search_results = search_images(user_query, top_k=2) # Tìm kiếm top 2 ảnh liên quan
        return jsonify({'results': search_results})
    
    except Exception as e:
        print(f"Error during image search: {e}")
        return jsonify({'error': 'Đã có lỗi xảy ra trong quá trình tìm kiếm hình ảnh.'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)