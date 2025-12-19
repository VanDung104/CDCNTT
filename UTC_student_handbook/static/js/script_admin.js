document.addEventListener("DOMContentLoaded", () => {
  // --- Biến cho Chat ---
  const qaForm = document.getElementById("qa-form");
  const questionInput = document.getElementById("question-input");
  const chatBox = document.getElementById("chat-box");
  const submitButton = document.getElementById("submit-button");
  const imageSearchButton = document.getElementById("image-search-button");

  // --- Biến cho Upload Modal ---
  const uploadPdfButton = document.getElementById("upload-pdf-button"); // Có thể là null
  const uploadModal = document.getElementById("upload-modal");
  const closeModalButton = document.getElementById("close-modal-button");
  const uploadPdfForm = document.getElementById("upload-pdf-form");
  const pdfFileInput = document.getElementById("pdf-file-input");
  const dateInput = document.getElementById("document-date-input"); // (MỚI) Input ngày
  const uploadStatus = document.getElementById("upload-status");
  const submitUploadButton = document.getElementById("submit-upload-button");

  // ===================================
  // --- XỬ LÝ CHAT VÀ TÌM KIẾM ---
  // ===================================

  qaForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleRequest("text");
  });

  imageSearchButton.addEventListener("click", (e) => {
    e.preventDefault();
    handleRequest("image");
  });

  async function handleRequest(type) {
    const question = questionInput.value.trim();
    if (!question) return;

    appendMessage(question, "user", []); // Câu hỏi của user không có source
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
        // (CẬP NHẬT) Gửi cả answer và sources
        appendMessage(data.answer, "bot", data.sources || []);
      } else {
        appendImageResults(data.results || []);
      }
    } catch (error) {
      if (typingIndicator) typingIndicator.remove();
      console.error("Fetch Error:", error);
      appendMessage(`**Lỗi:** ${error.message}`, "bot", []);
    } finally {
      setFormDisabled(false);
      questionInput.focus();
    }
  }

  /**
   * (CẬP NHẬT) Hiển thị tin nhắn và nguồn tham khảo
   */
  function appendMessage(text, type, sources = []) {
    const messageDiv = document.createElement("div");
    messageDiv.className = `chat-message ${type}`;
    
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    if (type === "bot") {
      contentDiv.innerHTML = marked.parse(text || "Không có câu trả lời.");
    } else {
      contentDiv.innerText = text;
    }
    
    messageDiv.appendChild(contentDiv);

    // (CẬP NHẬT) Hiển thị nguồn tham khảo chi tiết
    if (type === "bot" && sources.length > 0) {
      const sourcesDiv = document.createElement("div");
      sourcesDiv.className = "sources-container";
      let sourcesHtml = "<h6>📚 Nguồn tham khảo (ưu tiên mới nhất):</h6><ul>";
      
      sources.forEach(source => {
        // Lấy thông tin từ source (khớp với key trong app.py)
        const pageNum = source.page || 'N/A';
        const filename = source.filename || 'Không rõ';
        const date = source.date || 'Không rõ';
        
        sourcesHtml += `
          <li>
            <strong>Ngày:</strong> ${date} | 
            <strong>Nguồn:</strong> ${filename} |
            <strong>Trang:</strong> ${pageNum}
          </li>`;
      });
      sourcesHtml += "</ul>";
      sourcesDiv.innerHTML = sourcesHtml;
      
      contentDiv.appendChild(sourcesDiv);
    }

    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }
  
  // Hàm hiển thị kết quả hình ảnh
  function appendImageResults(results) {
    if (!results || results.length === 0) {
      appendMessage("Rất tiếc, tôi không tìm thấy hình ảnh nào phù hợp.", "bot", []);
      return;
    }

    const messageDiv = document.createElement("div");
    messageDiv.className = "chat-message bot";
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    
    let htmlContent = '';
    results.forEach(result => {
      const score = parseFloat(result.score).toFixed(4);
      htmlContent += `
        <div class="image-result-item">
            <p class="image-caption">Trang ${result.page_number} (Tương đồng: ${score})</p>
            <img src="${result.image_base64}" 
                alt="Kết quả tìm kiếm trang ${result.page_number}" 
                class="search-result-image"
                data-src="${result.image_base64}">
        </div>
      `;
    });

    contentDiv.innerHTML = htmlContent;
    messageDiv.appendChild(contentDiv);
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Thêm sự kiện click cho ảnh (sử dụng event delegation)
    contentDiv.addEventListener('click', (e) => {
        if (e.target.classList.contains('search-result-image')) {
            showImageModal(e.target.dataset.src);
        }
    });
  }

  // Hàm hiển thị modal phóng to ảnh
  function showImageModal(src) {
    let modal = document.getElementById('image-zoom-modal');
    if (modal) modal.remove();

    modal = document.createElement('div');
    modal.id = 'image-zoom-modal';
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
    if (uploadPdfButton) {
        uploadPdfButton.disabled = isDisabled;
    }
  }

  // ===================================
  // --- XỬ LÝ UPLOAD PDF (CHỈ KHI LÀ ADMIN) ---
  // ===================================

  // Chỉ gán sự kiện nếu nút upload tồn tại (tức là admin đã đăng nhập)
  if (uploadPdfButton) {
    // Mở modal
    uploadPdfButton.addEventListener("click", () => {
      uploadModal.style.display = "block";
      uploadStatus.innerHTML = ""; // Xóa trạng thái cũ
      pdfFileInput.value = null; // Xóa file đã chọn (nếu có)
      dateInput.value = ""; // Xóa ngày cũ
      submitUploadButton.disabled = false;
      submitUploadButton.innerText = "Tải lên";
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

    // (CẬP NHẬT) Hàm xử lý upload file
    async function handlePdfUpload() {
      const file = pdfFileInput.files[0];
      const documentDate = dateInput.value; // (MỚI) Lấy giá trị ngày

      if (!file) {
        uploadStatus.innerHTML = '<div class="alert alert-danger">Vui lòng chọn một file.</div>';
        return;
      }
      if (!documentDate) { // (MỚI) Kiểm tra ngày
        uploadStatus.innerHTML = '<div class="alert alert-danger">Vui lòng chọn ngày cho văn bản.</div>';
        return;
      }
      if (file.type !== "application/pdf") {
        uploadStatus.innerHTML = '<div class="alert alert-danger">Chỉ chấp nhận file PDF.</div>';
        return;
      }

      const formData = new FormData();
      formData.append("pdf_file", file); // Tên key phải khớp với Flask
      formData.append("document_date", documentDate); // (MỚI) Gửi cả ngày

      submitUploadButton.disabled = true;
      submitUploadButton.innerText = "Đang xử lý...";
      uploadStatus.innerHTML = '<div class="alert alert-info">Đang tải lên và xử lý file...</div>';

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
          
          // Thông báo cho người dùng khởi động lại server
          appendMessage("Một tài liệu mới đã được thêm vào. **Hệ thống sẽ cần khởi động lại** để cập nhật kiến thức. Vui lòng thông báo cho quản trị viên.", "bot", []);
        } else {
          throw new Error(data.error || "Lỗi không xác định từ server.");
        }

      } catch (error) {
        console.error("Upload Error:", error);
        uploadStatus.innerHTML = `<div class="alert alert-danger"><strong>Lỗi:</strong> ${error.message}</div>`;
      } finally {
        submitUploadButton.disabled = false;
        submitUploadButton.innerText = "Tải lên";
      }
    }
  } // Kết thúc khối 'if (uploadPdfButton)'
});