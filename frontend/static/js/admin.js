document.addEventListener("DOMContentLoaded", async () => {
  const usersContainer = document.getElementById("adminUsers");
  const documentsContainer = document.getElementById("adminDocuments");
  const userSearch = document.getElementById("userSearch");
  let users = [];

  function renderUsers() {
    const query = userSearch.value.trim().toLowerCase();
    const visibleUsers = users.filter((user) =>
      user.username.toLowerCase().includes(query) || user.email.toLowerCase().includes(query)
    );
    usersContainer.replaceChildren();
    if (!visibleUsers.length) {
      usersContainer.textContent = users.length ? "No accounts match your search." : "No user accounts have been created.";
      return;
    }
    visibleUsers.forEach((user) => {
      const row = document.createElement("div");
      row.className = "admin-user-row";
      const avatar = document.createElement("span");
      avatar.className = "avatar";
      avatar.textContent = user.username.slice(0, 1).toUpperCase();
      const info = document.createElement("span");
      info.className = "admin-user-info";
      const name = document.createElement("b");
      name.textContent = user.username;
      const email = document.createElement("small");
      email.textContent = user.email;
      info.append(name, email);
      const role = document.createElement("span");
      role.className = "role-badge";
      role.textContent = user.role;
      row.append(avatar, info, role);
      usersContainer.append(row);
    });
  }

  function renderDocuments(documents) {
    documentsContainer.replaceChildren();
    if (!documents.length) {
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.className = "admin-documents-empty";
      cell.textContent = "No documents have been uploaded.";
      const row = document.createElement("tr");
      row.append(cell);
      documentsContainer.append(row);
      return;
    }
    documents.forEach((docItem) => {
      const row = document.createElement("tr");
      const file = document.createElement("td");
      file.innerHTML = '<i class="bi bi-file-earmark-pdf admin-file-icon"></i>';
      const name = document.createElement("span");
      name.textContent = docItem.filename;
      file.append(name);
      const type = document.createElement("td");
      type.textContent = "PDF";
      const date = document.createElement("td");
      date.textContent = Satya.formatDate(docItem.upload_date);
      const status = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = `status-badge status-${docItem.processing_status}`;
      badge.textContent = docItem.processing_status;
      status.append(badge);
      row.append(file, type, date, status);
      documentsContainer.append(row);
    });
  }

  try {
    const [stats, directory] = await Promise.all([
      Satya.request("/api/admin/stats"),
      Satya.request("/api/admin/users")
    ]);
    document.getElementById("connectionLabel").textContent = "Application connected";
    document.getElementById("connectionIndicator").classList.add("connection-on");
    document.getElementById("databaseStatus").textContent = "Connected";
    document.getElementById("databaseIndicator").classList.add("connection-on");
    const extractionStatus = document.getElementById("extractionStatus");
    const extractionIndicator = document.getElementById("extractionIndicator");
    if (extractionStatus) {
      extractionStatus.textContent = stats.extraction_enabled ? "Enabled" : "Not enabled";
    }
    if (extractionIndicator) {
      extractionIndicator.classList.toggle("check-off", !stats.extraction_enabled);
      extractionIndicator.classList.toggle("connection-on", Boolean(stats.extraction_enabled));
    }
    const monitoringStatus = document.getElementById("monitoringStatus");
    const monitoringIndicator = document.getElementById("monitoringIndicator");
    if (monitoringStatus) {
      monitoringStatus.textContent = stats.monitoring_configured ? "Configured" : "Not configured";
    }
    if (monitoringIndicator) {
      monitoringIndicator.classList.toggle("check-off", !stats.monitoring_configured);
      monitoringIndicator.classList.toggle("connection-on", Boolean(stats.monitoring_configured));
    }
    const processingNote = document.getElementById("processingNote");
    if (processingNote) {
      processingNote.textContent = stats.extraction_enabled
        ? `${stats.processing_statuses.processed || 0} processed · extraction active`
        : "Processing is not enabled";
    }
    document.getElementById("userTotal").textContent = stats.total_users;
    document.getElementById("documentTotal").textContent = stats.total_documents;
    document.getElementById("processingTotal").textContent =
      (stats.processing_statuses.processing || 0) + (stats.processing_statuses.processed || 0);
    users = directory.users;
    renderUsers();
    userSearch.addEventListener("input", renderUsers);

    const statuses = document.getElementById("adminStatuses");
    statuses.replaceChildren();
    const statusEntries = Object.entries(stats.processing_statuses);
    if (!statusEntries.length) {
      statuses.textContent = "No document records are available.";
    } else {
      statusEntries.forEach(([status, total]) => {
        const row = document.createElement("div");
        row.className = "status-row";
        const badge = document.createElement("span");
        badge.className = `status-badge status-${status}`;
        badge.textContent = status;
        const count = document.createElement("b");
        count.textContent = total;
        row.append(badge, count);
        statuses.append(row);
      });
    }
    renderDocuments(stats.recent_documents);
  } catch (error) {
    document.getElementById("connectionLabel").textContent = error.message;
    document.getElementById("databaseStatus").textContent = "Unavailable";
    documentsContainer.innerHTML = `<tr><td colspan="4" class="table-error">${Satya.escape(error.message)}</td></tr>`;
    usersContainer.textContent = "Unable to load current account records.";
    document.getElementById("adminStatuses").textContent = "Unable to load current document status.";
  }
});
