document.addEventListener("DOMContentLoaded", () => {
  // --- Biến cho Chat ---
  const qaForm = document.getElementById("qa-form");
  const questionInput = document.getElementById("question-input");
  const chatBox = document.getElementById("chat-box");
  const submitButton = document.getElementById("submit-button");
  const imageSearchButton = document.getElementById("image-search-button");

  // --- Biến cho Upload Modal ---
  const uploadPdfButton = document.getElementById("upload-pdf-button");
  const uploadModal = document.getElementById("upload-modal");
  const closeModalButton = document.getElementById("close-modal-button");
  const uploadPdfForm = document.getElementById("upload-pdf-form");
  const pdfFileInput = document.getElementById("pdf-file-input");
  const uploadStatus = document.getElementById("upload-status");
  const submitUploadButton = document.getElementById("submit-upload-button");

  // ===================================
  // --- XỬ LÝ CHAT VÀ TÌM KIẾM ---
  // ===================================

  // Lắng nghe sự kiện submit form (nhấn Enter hoặc nút Gửi)
  qaForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleRequest("text");
  });

  // Lắng nghe sự kiện click trên nút Tìm ảnh
  imageSearchButton.addEventListener("click", (e) => {
    e.preventDefault();
    handleRequest("image");
  });

  // Hàm xử lý request chung
  async function handleRequest(type) {
    const question = questionInput.value.trim();
    if (!question) return;

    appendMessage(question, "user");
    questionInput.value = "";
    setFormDisabled(true);
    const typingIndicator = showTypingIndicator();

    const endpoint = type === "text" ? "/ask" : "/search_image";
    const body = type === "text" ? { question: question } : { query: question };

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      typingIndicator.remove();
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Lỗi không xác định từ server.");
      }

      if (type === "text") {
        // --- THAY ĐỔI: Chỉ truyền data.answer ---
        appendMessage(data.answer, "bot");
        // (data.sources vẫn tồn tại nhưng không được sử dụng ở đây)
      } else {
        appendImageResults(data.results);
      }
    } catch (error) {
      if (typingIndicator) typingIndicator.remove();
      console.error("Fetch Error:", error);
      appendMessage(`**Lỗi:** ${error.message}`, "bot");
    } finally {
      setFormDisabled(false);
      questionInput.focus();
    }
  }

  // --- HÀM ĐÃ CẬP NHẬT ---
  // Loại bỏ tham số 'sources' và logic hiển thị nguồn
  function appendMessage(text, type) {
    const messageDiv = document.createElement("div");
    messageDiv.className = `chat-message ${type}`;
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    if (type === "bot") {
      // Chỉ render Markdown cho câu trả lời
      contentDiv.innerHTML = marked.parse(text);
    } else {
      // Hiển thị text thuần túy cho người dùng
      contentDiv.innerText = text;
    }
    
    messageDiv.appendChild(contentDiv);
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }
  
  // Hàm hiển thị kết quả hình ảnh
  function appendImageResults(results) {
    if (!results || results.length === 0) {
      appendMessage("Rất tiếc, tôi không tìm thấy hình ảnh nào phù hợp.", "bot");
      return;
    }

    const messageDiv = document.createElement("div");
    messageDiv.className = "chat-message bot";
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    
    let htmlContent = '';
    results.forEach(result => {
      const score = parseFloat(result.score).toFixed(3);
      htmlContent += `
        <div>
            <p class="image-caption">Trang ${result.page_index} (Tương đồng: ${score})</p>
            <img src="${result.image_base64}" 
                alt="Kết quả tìm kiếm trang ${result.page_index}" 
                class="search-result-image">
        </div>
      `;
    });

    contentDiv.innerHTML = htmlContent;
    messageDiv.appendChild(contentDiv);
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Thêm sự kiện click cho ảnh
    contentDiv.querySelectorAll('.search-result-image').forEach(img => {
      img.addEventListener('click', () => {
        showImageModal(img.src);
      });
    });
  }

  // Hàm hiển thị modal phóng to ảnh
  function showImageModal(src) {
    const modal = document.createElement('div');
    modal.className = 'image-modal';
    
    const modalImg = document.createElement('img');
    modalImg.className = 'modal-content';
    modalImg.src = src;

    modal.appendChild(modalImg);
    document.body.appendChild(modal);
    modal.style.display = 'block';

    modal.addEventListener('click', () => {
      modal.style.display = 'none';
      document.body.removeChild(modal);
    });
  }

  // Hàm hiển thị "đang gõ"
  function showTypingIndicator() {
    const indicatorDiv = document.createElement("div");
    indicatorDiv.className = "chat-message bot";
    indicatorDiv.innerHTML = `
      <div class="message-content" style="padding: 12px 20px;">
        <div class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>`;
    chatBox.appendChild(indicatorDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    return indicatorDiv;
  }

  // Hàm bật/tắt form nhập liệu
  function setFormDisabled(isDisabled) {
    questionInput.disabled = isDisabled;
    submitButton.disabled = isDisabled;
    imageSearchButton.disabled = isDisabled;
    uploadPdfButton.disabled = isDisabled;
  }

  // ===================================
  // --- XỬ LÝ UPLOAD PDF ---
  // ===================================

  // Mở modal
  uploadPdfButton.addEventListener("click", () => {
    uploadModal.style.display = "block";
    uploadStatus.innerHTML = "";
    pdfFileInput.value = null;
  });

  // Đóng modal
  function closeModal() {
    uploadModal.style.display = "none";
  }
  closeModalButton.addEventListener("click", closeModal);
  window.addEventListener("click", (event) => {
    if (event.target == uploadModal) {
      closeModal();
    }
  });

  // Xử lý sự kiện submit form upload
  uploadPdfForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handlePdfUpload();
  });

  async function handlePdfUpload() {
    const file = pdfFileInput.files[0];
    if (!file) {
      uploadStatus.innerHTML = '<span class="text-danger">Vui lòng chọn một file.</span>';
      return;
    }

    if (file.type !== "application/pdf") {
      uploadStatus.innerHTML = '<span class="text-danger">Chỉ chấp nhận file PDF.</span>';
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    submitUploadButton.disabled = true;
    submitUploadButton.innerText = "Đang tải lên...";
    uploadStatus.innerHTML = '<span class="text-primary">Đang xử lý file...</span>';

    try {
      const response = await fetch("/upload_pdf", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (response.ok) {
        uploadStatus.innerHTML = `
          <div class="alert alert-success">
            <strong>Thành công!</strong><br>
            Đã thêm file: ${data.message.split(': ')[1]}<br>
            Số đoạn: ${data.chunks_added}<br>
            Ngày: ${data.date_added}
          </div>
        `;
        setTimeout(closeModal, 3000);
      } else {
        throw new Error(data.error || "Lỗi không xác định từ server.");
      }

    } catch (error) {
      console.error("Upload Error:", error);
      uploadStatus.innerHTML = `<span class="text-danger"><strong>Lỗi:</strong> ${error.message}</span>`;
    } finally {
      submitUploadButton.disabled = false;
      submitUploadButton.innerText = "Tải lên";
    }
  }
});