document.addEventListener("DOMContentLoaded", () => {
  const rows = document.getElementById("documentRows");
  if (!rows) return;
  const count = document.getElementById("documentCount");
  const search = document.getElementById("documentSearch");
  const filter = document.getElementById("documentStatusFilter");
  const canReview = rows.dataset.canVerify === "true";
  let documents = [];

  function render() {
    const query = search.value.trim().toLowerCase();
    const status = filter.value;
    const filtered = documents.filter((doc) => {
      const matchesSearch = doc.filename.toLowerCase().includes(query) ||
        doc.sources.some((source) => source.title.toLowerCase().includes(query));
      const matchesStatus = !status ||
        doc.processing_status === status ||
        doc.sources.some((source) => source.verification_status === status);
      return matchesSearch && matchesStatus;
    });
    rows.replaceChildren();
    if (!filtered.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.innerHTML = `<div class="empty-state table-empty"><span class="empty-icon"><i class="bi bi-file-earmark-x"></i></span><h4>${documents.length ? "No matching documents" : "No source documents uploaded yet."}</h4><p>${documents.length ? "Try another search or filter." : "Uploaded legal sources are extracted first, then reviewed before use in chat."}</p></div>`;
      tr.append(td);
      rows.append(tr);
      count.textContent = `${documents.length} document${documents.length === 1 ? "" : "s"}`;
      return;
    }
    filtered.forEach((doc) => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      const title = document.createElement("div");
      title.className = "document-name";
      const icon = document.createElement("i");
      icon.className = doc.document_type === "PDF" ? "bi bi-file-earmark-pdf" : "bi bi-file-earmark-text";
      const label = document.createElement("span");
      label.textContent = doc.filename;
      title.append(icon, label);
      name.append(title);
      const type = document.createElement("td");
      type.textContent = doc.document_type;
      const date = document.createElement("td");
      date.textContent = Satya.formatDate(doc.upload_date);
      const state = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = `status-badge status-${doc.processing_status}`;
      badge.textContent = doc.processing_status;
      state.append(badge);
      const action = document.createElement("td");
      action.className = "text-end";
      const link = document.createElement("a");
      link.className = "btn btn-sm btn-light";
      link.href = `/api/documents/${doc.id}/file`;
      link.target = "_blank";
      link.rel = "noopener";
      link.setAttribute("aria-label", `Open ${doc.filename}`);
      link.innerHTML = '<i class="bi bi-box-arrow-up-right"></i>';
      action.append(link);
      tr.append(name, type, date, state, action);
      rows.append(tr);
      (doc.sources || []).forEach((source) => {
        const sourceRow = document.createElement("tr");
        sourceRow.className = "document-source-row";
        const sourceCell = document.createElement("td");
        sourceCell.colSpan = 5;
        const card = document.createElement("div");
        card.className = "source-review-card";

        const heading = document.createElement("div");
        heading.className = "source-review-heading";
        const title = document.createElement("strong");
        title.textContent = source.title;
        const sourceStatus = document.createElement("span");
        sourceStatus.className = `status-badge status-${source.verification_status}`;
        sourceStatus.textContent = source.verification_status;
        heading.append(title, sourceStatus);

        const details = document.createElement("details");
        details.className = "source-review-preview";
        const summary = document.createElement("summary");
        summary.textContent = `${source.domain ? `${source.domain} · ` : ""}${source.chunk_count} extracted passage${source.chunk_count === 1 ? "" : "s"} · preview`;
        const preview = document.createElement("blockquote");
        preview.textContent = source.preview || "No text preview available.";
        details.append(summary, preview);

        const actions = document.createElement("div");
        actions.className = "source-review-actions";
        const original = document.createElement("a");
        original.className = "btn btn-sm btn-light";
        original.href = source.file_url;
        original.target = "_blank";
        original.rel = "noopener";
        original.textContent = "Open original file";
        actions.append(original);

        if (canReview && source.verification_status !== "verified") {
          const verify = document.createElement("button");
          verify.className = "btn btn-sm btn-outline-navy";
          verify.type = "button";
          verify.textContent = "Verify source";
          verify.addEventListener("click", () => reviewSource(source, "verify", verify));
          actions.append(verify);
        }
        if (canReview && source.verification_status !== "rejected") {
          const reject = document.createElement("button");
          reject.className = "btn btn-sm btn-outline-danger";
          reject.type = "button";
          reject.textContent = "Reject source";
          reject.addEventListener("click", () => reviewSource(source, "reject", reject));
          actions.append(reject);
        }

        card.append(heading, details, actions);
        sourceCell.append(card);
        sourceRow.append(sourceCell);
        rows.append(sourceRow);
      });
    });
    count.textContent = `${filtered.length} of ${documents.length} document${documents.length === 1 ? "" : "s"}`;
  }

  async function loadDocuments() {
    try {
      const result = await Satya.request("/api/documents");
      documents = result.documents;
      render();
    } catch (error) {
      rows.innerHTML = `<tr><td colspan="5"><div class="table-error">${Satya.escape(error.message)}</div></td></tr>`;
      count.textContent = "Could not load documents";
    }
  }

  async function reviewSource(source, decision, button) {
    const isVerify = decision === "verify";
    const action = isVerify ? "verify" : "reject";
    const message = isVerify
      ? `Confirm that you reviewed "${source.title}" against the original and checked the extracted text. This does not confirm that the law is current.`
      : `Reject "${source.title}" and exclude its passages from legal chat?`;
    if (!window.confirm(message)) return;
    button.disabled = true;
    try {
      const result = await Satya.request(
        `/api/legal-sources/${encodeURIComponent(source.id)}/${action}`,
        { method: "POST", body: JSON.stringify({}) }
      );
      Satya.notify(result.message);
      await loadDocuments();
    } catch (error) {
      Satya.notify(error.message, "error");
      button.disabled = false;
    }
  }

  search.addEventListener("input", render);
  filter.addEventListener("change", render);
  loadDocuments();

  const uploadButton = document.getElementById("uploadDocument");
  uploadButton?.addEventListener("click", async () => {
    const fileInput = document.getElementById("documentFile");
    const feedback = document.getElementById("uploadFeedback");
    const file = fileInput.files[0];
    if (!file) {
      feedback.textContent = "Choose a source file first.";
      feedback.className = "form-text text-danger mt-2";
      return;
    }
    const supportedExtension = /\.(pdf|txt|csv|tsv|xls)$/i.test(file.name);
    if (!supportedExtension) {
      feedback.textContent = "Supported formats are PDF, TXT, CSV, and TSV.";
      feedback.className = "form-text text-danger mt-2";
      return;
    }
    if (file.size > 16 * 1024 * 1024) {
      feedback.textContent = "The maximum upload size is 16 MB.";
      feedback.className = "form-text text-danger mt-2";
      return;
    }
    const data = new FormData();
    data.append("file", file);
    uploadButton.disabled = true;
    feedback.textContent = "Uploading and extracting source text...";
    feedback.className = "form-text mt-2";
    try {
      const result = await Satya.request("/api/documents", { method: "POST", body: data });
      feedback.textContent = result.message;
      feedback.className = "form-text text-success mt-2";
      Satya.notify(result.message);
      fileInput.value = "";
      await loadDocuments();
      window.setTimeout(() => bootstrap.Modal.getOrCreateInstance(document.getElementById("uploadModal")).hide(), 900);
    } catch (error) {
      feedback.textContent = error.message;
      feedback.className = "form-text text-danger mt-2";
    } finally {
      uploadButton.disabled = false;
    }
  });
});
