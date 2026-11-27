document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chatForm");
  if (!form) return;

  const messages = document.getElementById("chatMessages");
  const input = document.getElementById("chatInput");
  const send = document.getElementById("sendButton");
  const history = document.getElementById("conversationList");
  const newButton = document.getElementById("newConversation");
  const clearButton = document.getElementById("clearConversation");
  const evidencePanel = document.getElementById("evidencePanel");
  const evidenceContent = document.getElementById("evidenceContent");
  const evidenceTitleEl = evidencePanel?.querySelector(".evidence-header b");
  const evidenceSubtitleEl = evidencePanel?.querySelector(".evidence-header small");
  const evidenceFooterEl = evidencePanel?.querySelector(".evidence-footer");
  const knowledgeStatus = document.getElementById("knowledgeStatus") || document.querySelector(".knowledge-status");
  const composerDisclaimer = document.querySelector(".composer-disclaimer");
  const languageSelect = document.getElementById("chatLanguage");
  const LANGUAGE_STORAGE_KEY = "satya_chat_language";
  const SUPPORTED_LANGUAGES = new Set(["en", "kn", "hi"]);
  const EVIDENCE_UI = {
    en: {
      panelTitle: "Evidence panel",
      panelSubtitle: "Source provenance for this response",
      evidenceFooter: "Answers use only retrieved verified source passages.",
      insufficientBadge: "INSUFFICIENT EVIDENCE",
      noAnswerBadge: "NO ANSWER GENERATED",
      nothingToCite: "Nothing to cite yet.",
      noSourceReturned: "No verified source evidence was returned for this response. Satya will not fabricate legal sections, citations or quotations.",
      unverifiedCannotGenerate: "Satya could not generate a verifiable answer from the available sources.",
      inspectionNote: "Retrieved source records are shown for inspection; they do not support a generated answer.",
      sourceDocument: "Source document",
      actOrRule: "Act or Rule",
      section: "Section",
      sectionOrParagraph: "Section / paragraph",
      paragraph: "Paragraph",
      page: "Page",
      notAvailable: "Not available",
      notSpecified: "Not specified",
      viewSourceLibrary: "View source library",
      openSourceUrl: "Open source URL",
      openSourceDoc: "Open source document",
      checkingEvidence: "Checking available evidence",
      youLabel: "You",
      copyLabel: "Copy",
      copiedLabel: "Copied",
      copyAriaLabel: "Copy Satya's response",
      clipboardUnavailable: "Clipboard unavailable",
      evidenceButtonLabel: "Evidence",
      historyEmpty: "Your conversations will appear here.",
      inputPlaceholder: "Ask a question about Indian law or policy...",
      disclaimerBase: "SATYA can make mistakes. Check the original source.",
      disclaimerNoDocs: " No verified legal documents are available yet.",
      knowledgeReady: (count) => ` Knowledge base ready · ${count} verified source${count === 1 ? "" : "s"}`,
      knowledgeUnavailable: " Knowledge base unavailable",
      newConversationEyebrow: "NEW CONVERSATION",
      newConversationTitleHtml: "Clarity begins<br>with <em>good questions.</em>",
      clearedEyebrow: "CONVERSATION CLEARED",
      clearedTitleHtml: "Start with a<br><em>new question.</em>",
      welcomeReadyBody: "Answers use retrieved passages from verified legal source documents.",
      welcomeEmptyBody: "No verified legal documents are available yet. An administrator must review and verify extracted sources before Satya can answer.",
      clearConfirm: "Clear this conversation?",
      networkError: "Unable to reach the server. Please check your connection and try again."
    },
    kn: {
      panelTitle: "ಪುರಾವೆ ಫಲಕ",
      panelSubtitle: "ಈ ಉತ್ತರದ ಮೂಲ ಆಧಾರ ವಿವರಗಳು",
      evidenceFooter: "ಉತ್ತರಗಳು ಮರುಪಡೆಯಲಾದ ಪರಿಶೀಲಿಸಿದ ಮೂಲ ಭಾಗಗಳನ್ನು ಮಾತ್ರ ಬಳಸುತ್ತವೆ.",
      insufficientBadge: "ಸಾಕಷ್ಟು ಪುರಾವೆ ಲಭ್ಯವಿಲ್ಲ",
      noAnswerBadge: "ಉತ್ತರ ರಚಿಸಲಾಗಿಲ್ಲ",
      nothingToCite: "ಇನ್ನೂ ಉಲ್ಲೇಖಿಸಲು ಏನೂ ಇಲ್ಲ.",
      noSourceReturned: "ಈ ಪ್ರಶ್ನೆಗೆ ಪರಿಶೀಲಿಸಿದ ಮೂಲ ಪುರಾವೆ ಕಂಡುಬಂದಿಲ್ಲ. SATYA ಕಾನೂನು ವಿಭಾಗಗಳು, ಉಲ್ಲೇಖಗಳು ಅಥವಾ ವಾಕ್ಯಗಳನ್ನು ಕಲ್ಪಿಸಿ ಹೇಳುವುದಿಲ್ಲ.",
      unverifiedCannotGenerate: "ಲಭ್ಯವಿರುವ ಮೂಲಗಳಿಂದ ಪರಿಶೀಲಿಸಬಹುದಾದ ಉತ್ತರವನ್ನು ರಚಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ.",
      inspectionNote: "ಪರಿಶೀಲನೆಗಾಗಿ ಮರುಪಡೆಯಲಾದ ಮೂಲ ದಾಖಲೆಗಳನ್ನು ತೋರಿಸಲಾಗಿದೆ; ಅವು ರಚಿತ ಉತ್ತರವನ್ನು ಬೆಂಬಲಿಸುವುದಿಲ್ಲ.",
      sourceDocument: "ಮೂಲ ದಾಖಲೆ",
      actOrRule: "ಕಾಯ್ದೆ ಅಥವಾ ನಿಯಮ",
      section: "ವಿಭಾಗ / ನಿಯಮ",
      sectionOrParagraph: "ವಿಭಾಗ / ಪ್ಯಾರಾ",
      paragraph: "ಪ್ಯಾರಾ",
      page: "ಪುಟ",
      notAvailable: "ಲಭ್ಯವಿಲ್ಲ",
      notSpecified: "ನಿರ್ದಿಷ್ಟಪಡಿಸಲಾಗಿಲ್ಲ",
      viewSourceLibrary: "ಮೂಲ ಗ್ರಂಥಾಲಯ ನೋಡಿ",
      openSourceUrl: "ಮೂಲ URL ತೆರೆಯಿರಿ",
      openSourceDoc: "ಮೂಲ ದಾಖಲೆ ತೆರೆಯಿರಿ",
      checkingEvidence: "ಲಭ್ಯವಿರುವ ಪುರಾವೆಗಳನ್ನು ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ",
      youLabel: "ನೀವು",
      copyLabel: "ನಕಲಿಸಿ",
      copiedLabel: "ನಕಲಿಸಲಾಗಿದೆ",
      copyAriaLabel: "SATYA ಉತ್ತರವನ್ನು ನಕಲಿಸಿ",
      clipboardUnavailable: "ಕ್ಲಿಪ್‌ಬೋರ್ಡ್ ಲಭ್ಯವಿಲ್ಲ",
      evidenceButtonLabel: "ಪುರಾವೆ",
      historyEmpty: "ನಿಮ್ಮ ಸಂಭಾಷಣೆಗಳು ಇಲ್ಲಿ ಕಾಣಿಸುತ್ತವೆ.",
      inputPlaceholder: "ಭಾರತೀಯ ಕಾನೂನು ಅಥವಾ ನೀತಿಯ ಕುರಿತು ಪ್ರಶ್ನೆ ಕೇಳಿ...",
      disclaimerBase: "SATYA ತಪ್ಪುಗಳನ್ನು ಮಾಡಬಹುದು. ದಯವಿಟ್ಟು ಮೂಲ ದಾಖಲೆಯನ್ನು ಪರಿಶೀಲಿಸಿ.",
      disclaimerNoDocs: " ಇನ್ನೂ ಯಾವುದೇ ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ದಾಖಲೆಗಳು ಲಭ್ಯವಿಲ್ಲ.",
      knowledgeReady: (count) => ` ಜ್ಞಾನಕೋಶ ಸಿದ್ಧವಾಗಿದೆ · ${count} ಪರಿಶೀಲಿಸಿದ ಮೂಲ${count === 1 ? "" : "ಗಳು"}`,
      knowledgeUnavailable: " ಜ್ಞಾನಕೋಶ ಲಭ್ಯವಿಲ್ಲ",
      newConversationEyebrow: "ಹೊಸ ಸಂಭಾಷಣೆ",
      newConversationTitleHtml: "ಸ್ಪಷ್ಟತೆ <em>ಉತ್ತಮ ಪ್ರಶ್ನೆಗಳಿಂದ</em> ಆರಂಭವಾಗುತ್ತದೆ.",
      clearedEyebrow: "ಸಂಭಾಷಣೆ ತೆರವುಗೊಳಿಸಲಾಗಿದೆ",
      clearedTitleHtml: "<em>ಹೊಸ ಪ್ರಶ್ನೆಯೊಂದಿಗೆ</em> ಆರಂಭಿಸಿ.",
      welcomeReadyBody: "ಉತ್ತರಗಳು ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ಮೂಲ ದಾಖಲೆಗಳಿಂದ ಪಡೆದ ಭಾಗಗಳನ್ನು ಮಾತ್ರ ಬಳಸುತ್ತವೆ.",
      welcomeEmptyBody: "ಇನ್ನೂ ಯಾವುದೇ ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ದಾಖಲೆಗಳು ಲಭ್ಯವಿಲ್ಲ. SATYA ಉತ್ತರಿಸುವ ಮೊದಲು ನಿರ್ವಾಹಕರು ಮೂಲಗಳನ್ನು ಪರಿಶೀಲಿಸಿ ದೃಢೀಕರಿಸಬೇಕು.",
      clearConfirm: "ಈ ಸಂಭಾಷಣೆಯನ್ನು ತೆರವುಗೊಳಿಸಬೇಕೇ?",
      networkError: "ಸರ್ವರ್‌ಗೆ ಸಂಪರ್ಕಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಸಂಪರ್ಕವನ್ನು ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
    },
    hi: {
      panelTitle: "साक्ष्य पैनल",
      panelSubtitle: "इस उत्तर के स्रोत प्रमाण विवरण",
      evidenceFooter: "उत्तर केवल प्राप्त सत्यापित स्रोत अंशों का उपयोग करते हैं।",
      insufficientBadge: "अपर्याप्त साक्ष्य",
      noAnswerBadge: "उत्तर तैयार नहीं किया गया",
      nothingToCite: "अभी उद्धृत करने के लिए कुछ नहीं है।",
      noSourceReturned: "इस उत्तर के लिए कोई सत्यापित स्रोत साक्ष्य नहीं मिला। SATYA कानूनी धाराएँ, उद्धरण या पाठ मनगढ़ंत नहीं बनाएगा।",
      unverifiedCannotGenerate: "उपलब्ध स्रोतों से सत्यापित किया जा सकने वाला उत्तर तैयार नहीं किया जा सका।",
      inspectionNote: "निरीक्षण के लिए प्राप्त स्रोत रिकॉर्ड दिखाए गए हैं; वे किसी तैयार उत्तर का समर्थन नहीं करते।",
      sourceDocument: "स्रोत दस्तावेज़",
      actOrRule: "अधिनियम या नियम",
      section: "धारा / नियम",
      sectionOrParagraph: "धारा / अनुच्छेद",
      paragraph: "अनुच्छेद",
      page: "पृष्ठ",
      notAvailable: "उपलब्ध नहीं",
      notSpecified: "निर्दिष्ट नहीं",
      viewSourceLibrary: "स्रोत लाइब्रेरी देखें",
      openSourceUrl: "स्रोत URL खोलें",
      openSourceDoc: "स्रोत दस्तावेज़ खोलें",
      checkingEvidence: "उपलब्ध साक्ष्यों की जांच की जा रही है",
      youLabel: "आप",
      copyLabel: "कॉपी करें",
      copiedLabel: "कॉपी हो गया",
      copyAriaLabel: "SATYA का उत्तर कॉपी करें",
      clipboardUnavailable: "क्लिपबोर्ड उपलब्ध नहीं है",
      evidenceButtonLabel: "साक्ष्य",
      historyEmpty: "आपकी बातचीत यहाँ दिखाई देगी।",
      inputPlaceholder: "भारतीय कानून या नीति से जुड़ा प्रश्न पूछें...",
      disclaimerBase: "SATYA से त्रुटि हो सकती है। कृपया मूल स्रोत अवश्य जांचें।",
      disclaimerNoDocs: " अभी कोई सत्यापित कानूनी दस्तावेज़ उपलब्ध नहीं हैं।",
      knowledgeReady: (count) => ` ज्ञानकोष तैयार है · ${count} सत्यापित स्रोत`,
      knowledgeUnavailable: " ज्ञानकोष अनुपलब्ध है",
      newConversationEyebrow: "नया संवाद",
      newConversationTitleHtml: "स्पष्टता <em>सही प्रश्नों</em> से शुरू होती है।",
      clearedEyebrow: "संवाद साफ़ किया गया",
      clearedTitleHtml: "<em>नए प्रश्न</em> के साथ शुरू करें।",
      welcomeReadyBody: "उत्तर केवल सत्यापित कानूनी स्रोत दस्तावेज़ों से प्राप्त अंशों का उपयोग करते हैं।",
      welcomeEmptyBody: "अभी कोई सत्यापित कानूनी दस्तावेज़ उपलब्ध नहीं हैं। SATYA द्वारा उत्तर देने से पहले प्रशासक को स्रोतों की समीक्षा और सत्यापन करना होगा।",
      clearConfirm: "क्या इस संवाद को साफ़ करना है?",
      networkError: "सर्वर से संपर्क नहीं हो सका। कृपया अपना कनेक्शन जांचें और पुनः प्रयास करें।"
    }
  };
  let conversationId = null;
  let busy = false;
  let lastEvidenceState = undefined;
  let lastKnowledgeStatus = null;
  let selectedLanguage = (() => {
    try {
      const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
      if (saved && SUPPORTED_LANGUAGES.has(saved)) return saved;
    } catch (_error) {}
    return "en";
  })();

  function detectQuestionLanguage(text) {
    const raw = String(text || "");
    if (/[\u0C80-\u0CFF]/.test(raw)) return "kn";
    if (/[\u0900-\u097F]/.test(raw)) return "hi";
    return null;
  }

  function activeLanguage() {
    if (languageSelect && SUPPORTED_LANGUAGES.has(languageSelect.value)) {
      selectedLanguage = languageSelect.value;
    }
    return selectedLanguage;
  }

  function uiLabels(lang = null) {
    return EVIDENCE_UI[lang || activeLanguage()] || EVIDENCE_UI.en;
  }

  function formatClientError(error, lang = null) {
    const raw = safeValue(error?.message || "").trim();
    if (!raw || raw === "Failed to fetch" || raw === "Load failed" || raw.startsWith("NetworkError")) {
      return uiLabels(lang).networkError;
    }
    return raw;
  }

  function syncEvidenceHeaders(lang = null) {
    const labels = uiLabels(lang);
    if (evidenceTitleEl) evidenceTitleEl.textContent = labels.panelTitle;
    if (evidenceSubtitleEl) evidenceSubtitleEl.textContent = labels.panelSubtitle;
    if (evidenceFooterEl) {
      evidenceFooterEl.innerHTML = `<i class="bi bi-shield-lock"></i> ${labels.evidenceFooter}`;
    }
  }

  function syncComposerText() {
    const labels = uiLabels();
    if (input) input.placeholder = labels.inputPlaceholder;
    if (composerDisclaimer) {
      const available = knowledgeStatus?.dataset.available === "true";
      composerDisclaimer.textContent = labels.disclaimerBase + (available ? "" : labels.disclaimerNoDocs);
    }
  }

  function syncWelcomeText() {
    const welcomeEl = document.getElementById("chatWelcome");
    if (!welcomeEl) return;
    const lang = activeLanguage();
    const copy = {
      en: {
        eyebrow: "EXECUTIVE RESEARCH COMPANION",
        titleHtml: "Clarity begins<br>with <em>good questions.</em>",
        desc: "Explore Indian law and policy with an assistant engineered to put verified evidence first and surface uncertainty transparently.",
        card1Title: "How does Satya work?",
        card1Sub: "Learn about evidence and citations",
        card2Title: "Explore legal topics",
        card2Sub: "See available knowledge domains"
      },
      kn: {
        eyebrow: "ಕಾನೂನು ಸಂಶೋಧನಾ ಸಹಾಯಕ",
        titleHtml: "ಸ್ಪಷ್ಟತೆ <em>ಉತ್ತಮ ಪ್ರಶ್ನೆಗಳಿಂದ</em> ಆರಂಭವಾಗುತ್ತದೆ.",
        desc: "ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ಪುರಾವೆಗಳನ್ನು ಮೊದಲ ಸ್ಥಾನದಲ್ಲಿಟ್ಟು ಪಾರದರ್ಶಕವಾಗಿ ಮಾಹಿತಿ ನೀಡುವ ಭಾರತೀಯ ಕಾನೂನು ಸಹಾಯಕ.",
        card1Title: "SATYA ಹೇಗೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ?",
        card1Sub: "ಪುರಾವೆ ಮತ್ತು ಉಲ್ಲೇಖಗಳ ಬಗ್ಗೆ ತಿಳಿಯಿರಿ",
        card2Title: "ಕಾನೂನು ವಿಷಯಗಳನ್ನು ಅನ್ವೇಷಿಸಿ",
        card2Sub: "ಲಭ್ಯವಿರುವ ಜ್ಞಾನ ಕ್ಷೇತ್ರಗಳನ್ನು ನೋಡಿ"
      },
      hi: {
        eyebrow: "कार्यकारी विधिक अनुसंधान सहायक",
        titleHtml: "स्पष्टता <em>सही प्रश्नों</em> से शुरू होती है।",
        desc: "सत्यापित साक्ष्यों को प्राथमिकता देने और अनिश्चितता को पारदर्शी रूप से दिखाने के लिए निर्मित भारतीय कानून सहायक।",
        card1Title: "SATYA कैसे काम करता है?",
        card1Sub: "साक्ष्य और उद्धरणों के बारे में जानें",
        card2Title: "कानूनी विषय देखें",
        card2Sub: "उपलब्ध ज्ञान क्षेत्र देखें"
      }
    }[lang] || {};
    const eyebrow = welcomeEl.querySelector(".welcome-eyebrow");
    const h1 = welcomeEl.querySelector("h1");
    const p = welcomeEl.querySelector(":scope > p");
    const cards = welcomeEl.querySelectorAll(".suggestion-card");
    if (eyebrow && copy.eyebrow) eyebrow.textContent = copy.eyebrow;
    if (h1 && copy.titleHtml) h1.innerHTML = copy.titleHtml;
    if (p && copy.desc) p.textContent = copy.desc;
    if (cards[0]) {
      const b = cards[0].querySelector("b");
      const small = cards[0].querySelector("small");
      if (b) b.textContent = copy.card1Title;
      if (small) small.textContent = copy.card1Sub;
    }
    if (cards[1]) {
      const b = cards[1].querySelector("b");
      const small = cards[1].querySelector("small");
      if (b) b.textContent = copy.card2Title;
      if (small) small.textContent = copy.card2Sub;
    }
  }

  function syncLanguageUI() {
    syncEvidenceHeaders();
    syncComposerText();
    syncWelcomeText();
    if (lastKnowledgeStatus) {
      renderKnowledgeStatus(lastKnowledgeStatus);
    } else if (knowledgeStatus && activeLanguage() !== "en") {
      const available = knowledgeStatus.dataset.available === "true";
      renderKnowledgeStatus({ available, verified_sources: available ? 1 : 0 });
    }
    if (lastEvidenceState !== undefined) {
      setEvidenceState(lastEvidenceState);
    } else if (activeLanguage() !== "en") {
      setEvidenceState();
    }
  }

  if (languageSelect) {
    languageSelect.value = selectedLanguage;
    languageSelect.addEventListener("change", () => {
      const nextLang = SUPPORTED_LANGUAGES.has(languageSelect.value) ? languageSelect.value : "en";
      selectedLanguage = nextLang;
      languageSelect.value = nextLang;
      try {
        window.localStorage.setItem(LANGUAGE_STORAGE_KEY, nextLang);
      } catch (_error) {}
      syncLanguageUI();
    });
  }
  syncLanguageUI();

  const safeValue = (value) => String(value ?? "");

  function inlineMarkdown(value) {
    return safeValue(value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }

  function markdownMarkup(value) {
    const lines = safeValue(value).split(/\r?\n/);
    const output = [];
    let listOpen = false;
    lines.forEach((line) => {
      const item = line.match(/^\s*[-*]\s+(.+)$/);
      if (item) {
        if (!listOpen) output.push("<ul>");
        listOpen = true;
        output.push(`<li>${inlineMarkdown(item[1])}</li>`);
        return;
      }
      if (listOpen) {
        output.push("</ul>");
        listOpen = false;
      }
      if (!line.trim()) return;
      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        const level = Math.min(heading[1].length + 2, 5);
        output.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      } else {
        output.push(`<p>${inlineMarkdown(line)}</p>`);
      }
    });
    if (listOpen) output.push("</ul>");
    return output.join("");
  }

  function setBusy(value) {
    busy = value;
    send.disabled = value;
    input.disabled = value;
    send.innerHTML = value
      ? '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>'
      : '<i class="bi bi-arrow-up"></i>';
  }

  function setEvidenceState({ sources = [], citations = [], verified = false, evidence_status = "", language = null } = {}) {
    const panelLang = SUPPORTED_LANGUAGES.has(language) ? language : activeLanguage();
    lastEvidenceState = { sources, citations, verified, evidence_status, language: panelLang };
    const labels = uiLabels(panelLang);
    syncEvidenceHeaders(panelLang);
    const evidence = Array.from(
      new Map([...sources, ...citations].map((source) => [source.id || JSON.stringify(source), source])).values()
    );
    evidenceContent.replaceChildren();
    if (!evidence.length) {
      const empty = document.createElement("div");
      empty.className = "evidence-empty";
      const noEvidence = evidence_status === "insufficient_evidence";
      empty.innerHTML = `<span class="evidence-empty-icon"><i class="bi bi-file-earmark-x"></i></span><span class="insufficient-badge"><i class="bi bi-exclamation-circle"></i> ${noEvidence ? labels.insufficientBadge : labels.noAnswerBadge}</span><h2>${labels.nothingToCite}</h2><p>${noEvidence ? labels.noSourceReturned : labels.unverifiedCannotGenerate}</p><div class="evidence-fields"><div><span>${labels.sourceDocument}</span><b>${labels.notAvailable}</b></div><div><span>${labels.actOrRule}</span><b>${labels.notAvailable}</b></div><div><span>${labels.sectionOrParagraph}</span><b>${labels.notAvailable}</b></div><div><span>${labels.page}</span><b>${labels.notAvailable}</b></div></div><a href="/documents">${labels.viewSourceLibrary} <i class="bi bi-arrow-up-right"></i></a>`;
      evidenceContent.append(empty);
      return;
    }

    if (!verified) {
      const notice = document.createElement("p");
      notice.className = "evidence-status-note";
      notice.textContent = labels.inspectionNote;
      evidenceContent.append(notice);
    }

    evidence.forEach((source, index) => {
      const item = document.createElement("details");
      item.className = "evidence-source";
      if (index === 0) item.open = true;
      const summary = document.createElement("summary");
      const documentName = safeValue(source.filename || source.document_name || source.title || "Source document");
      const pageValue = source.page_range || (source.page ?? source.page_number);
      const subsectionText = source.subsection
        ? (String(source.subsection).startsWith("(") ? String(source.subsection) : `(${source.subsection})`)
        : "";
      const sectionLabel = [
        source.section,
        source.section && subsectionText ? subsectionText : "",
        source.section && source.section_title ? `— ${source.section_title}` : ""
      ].filter(Boolean).join(" ");
      const summarySection = [source.section ? `Rule/Sec ${source.section}` : "", source.paragraph, pageValue !== null && pageValue !== undefined && pageValue !== "" ? `p. ${pageValue}` : ""].filter(Boolean).join(" · ") || "Source reference";
      const sourceName = document.createElement("span");
      sourceName.className = "evidence-source-name";
      sourceName.innerHTML = '<i class="bi bi-file-earmark-text"></i>';
      const label = document.createElement("b");
      label.textContent = documentName;
      sourceName.append(label);
      const section = document.createElement("small");
      section.textContent = summarySection;
      summary.append(sourceName, section, document.createElement("i"));
      item.append(summary);

      const meta = document.createElement("div");
      meta.className = "evidence-source-meta";
      [
        [labels.sourceDocument, documentName],
        [labels.actOrRule, source.act_name || source.document_title],
        [labels.section, sectionLabel],
        [labels.paragraph, source.paragraph],
        [labels.page, pageValue]
      ].forEach(([key, value]) => {
        const row = document.createElement("div");
        const name = document.createElement("span");
        name.textContent = key;
        const content = document.createElement("b");
        content.textContent = value !== null && value !== undefined && value !== "" ? String(value) : labels.notSpecified;
        row.append(name, content);
        meta.append(row);
      });
      const supportingPassage = source.passage || source.excerpt;
      if (supportingPassage) {
        const excerpt = document.createElement("blockquote");
        excerpt.textContent = supportingPassage;
        meta.append(excerpt);
      }
      if (source.source_url) {
        const link = document.createElement("a");
        link.href = source.source_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = labels.openSourceUrl;
        meta.append(link);
      } else if (source.file_url) {
        const link = document.createElement("a");
        link.href = source.file_url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = labels.openSourceDoc;
        meta.append(link);
      }
      item.append(meta);
      evidenceContent.append(item);
    });
  }

  function addMessage(sender, text, timestamp = new Date(), evidence = null, lang = null) {
    document.getElementById("chatWelcome")?.remove();
    const messageLang = SUPPORTED_LANGUAGES.has(lang) ? lang : activeLanguage();
    const labels = uiLabels(messageLang);
    const row = document.createElement("article");
    row.className = `chat-message chat-message-${sender}`;
    const avatar = document.createElement("span");
    avatar.className = sender === "user" ? "chat-message-avatar user-message-avatar" : "chat-message-avatar ai-message-avatar";
    avatar.innerHTML = sender === "user" ? '<i class="bi bi-person"></i>' : '<i class="bi bi-stars"></i>';
    const body = document.createElement("div");
    body.className = "chat-message-body";
    const meta = document.createElement("div");
    meta.className = "chat-message-meta";
    const name = document.createElement("b");
    name.textContent = sender === "user" ? labels.youLabel : "SATYA";
    const time = document.createElement("time");
    time.dateTime = timestamp instanceof Date ? timestamp.toISOString() : timestamp;
    time.textContent = new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    meta.append(name, time);
    const content = document.createElement("div");
    content.className = "chat-message-content";
    content.innerHTML = sender === "assistant" ? markdownMarkup(text) : `<p>${inlineMarkdown(text)}</p>`;
    body.append(meta, content);

    if (sender === "assistant") {
      const actions = document.createElement("div");
      actions.className = "message-actions";
      const copy = document.createElement("button");
      copy.type = "button";
      copy.innerHTML = `<i class="bi bi-copy"></i> ${labels.copyLabel}`;
      copy.setAttribute("aria-label", labels.copyAriaLabel);
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(text);
          copy.innerHTML = `<i class="bi bi-check2"></i> ${labels.copiedLabel}`;
          window.setTimeout(() => { copy.innerHTML = `<i class="bi bi-copy"></i> ${uiLabels().copyLabel}`; }, 1400);
        } catch (_error) {
          copy.textContent = uiLabels().clipboardUnavailable;
        }
      });
      actions.append(copy);
      if (evidence) {
        const evidenceButton = document.createElement("button");
        evidenceButton.type = "button";
        evidenceButton.innerHTML = `<i class="bi bi-journal-text"></i> ${labels.evidenceButtonLabel}`;
        evidenceButton.addEventListener("click", () => {
          evidencePanel.classList.add("evidence-open");
          setEvidenceState(evidence);
        });
        actions.append(evidenceButton);
      }
      body.append(actions);
    }

    row.append(avatar, body);
    messages.append(row);
    messages.scrollTop = messages.scrollHeight;
  }

  function addTyping(lang = null) {
    const row = document.createElement("div");
    row.className = "chat-message chat-message-assistant";
    row.id = "typingIndicator";
    row.innerHTML = `<span class="chat-message-avatar ai-message-avatar"><i class="bi bi-stars"></i></span><div class="chat-message-body"><div class="chat-message-meta"><b>SATYA</b><span>${uiLabels(lang).checkingEvidence}</span></div><div class="typing-bubble"><span></span><span></span><span></span></div></div>`;
    messages.append(row);
    messages.scrollTop = messages.scrollHeight;
  }

  async function loadHistory() {
    try {
      const result = await Satya.request("/api/conversations");
      history.replaceChildren();
      if (!result.conversations.length) {
        const empty = document.createElement("p");
        empty.className = "history-empty";
        empty.textContent = uiLabels().historyEmpty;
        history.append(empty);
        return;
      }
      result.conversations.forEach((conversation) => {
        const button = document.createElement("button");
        button.className = "history-conversation";
        button.type = "button";
        button.dataset.id = conversation.id;
        const icon = document.createElement("i");
        icon.className = "bi bi-chat-left-text";
        const title = document.createElement("span");
        title.textContent = conversation.title;
        button.append(icon, title);
        button.addEventListener("click", () => openConversation(conversation.id));
        history.append(button);
      });
    } catch (error) {
      history.textContent = formatClientError(error);
    }
  }

  async function openConversation(id) {
    try {
      const result = await Satya.request(`/api/conversations/${id}`);
      conversationId = result.conversation.id;
      messages.replaceChildren();
      result.conversation.messages.forEach((message) => addMessage(message.sender, message.message, message.created_at));
      setEvidenceState();
      clearButton.disabled = false;
      history.querySelectorAll(".history-conversation").forEach((item) => item.classList.toggle("active", item.dataset.id === String(id)));
    } catch (error) {
      addMessage("assistant", formatClientError(error));
    }
  }

  async function sendMessage(text) {
    if (busy || !text.trim()) return;
    const question = text.trim();
    const turnLanguage = detectQuestionLanguage(question) || activeLanguage();
    addMessage("user", question, new Date(), null, turnLanguage);
    input.value = "";
    setBusy(true);
    addTyping(turnLanguage);
    try {
      const status = await Satya.request("/api/knowledge/status", {
        headers: { "X-Satya-Language": turnLanguage }
      });
      renderKnowledgeStatus(status);
      const result = await Satya.request("/api/chat", {
        method: "POST",
        headers: { "X-Satya-Language": turnLanguage },
        body: JSON.stringify({
          message: question,
          conversation_id: conversationId,
          language: turnLanguage
        })
      });
      const responseLanguage = SUPPORTED_LANGUAGES.has(result.language) ? result.language : turnLanguage;
      conversationId = result.conversation_id;
      document.getElementById("typingIndicator")?.remove();
      const evidence = {
        sources: result.sources || [],
        citations: result.citations || [],
        verified: result.verified === true,
        evidence_status: result.evidence_status || "",
        language: responseLanguage
      };
      addMessage("assistant", result.answer, new Date(), evidence, responseLanguage);
      setEvidenceState(evidence);
      clearButton.disabled = false;
      await loadHistory();
      history.querySelector(`[data-id="${conversationId}"]`)?.classList.add("active");
    } catch (error) {
      document.getElementById("typingIndicator")?.remove();
      addMessage("assistant", formatClientError(error, turnLanguage), new Date(), null, turnLanguage);
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(input.value);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  document.querySelectorAll(".suggestion-card").forEach((button) => {
    button.addEventListener("click", () => sendMessage(button.dataset.prompt || ""));
  });
  newButton.addEventListener("click", async () => {
    try {
      const result = await Satya.request("/api/conversations", { method: "POST", body: JSON.stringify({}) });
      conversationId = result.conversation.id;
      messages.replaceChildren();
      const welcome = document.createElement("div");
      welcome.className = "chat-welcome";
      const hasVerifiedSources = knowledgeStatus?.dataset.available === "true";
      const labels = uiLabels();
      welcome.innerHTML = `<div class="welcome-symbol"><span class="welcome-symbol-inner"><i class="bi bi-stars"></i></span><span class="welcome-ring"></span></div><div class="welcome-eyebrow">${labels.newConversationEyebrow}</div><h1>${labels.newConversationTitleHtml}</h1><p>${hasVerifiedSources ? labels.welcomeReadyBody : labels.welcomeEmptyBody}</p>`;
      messages.append(welcome);
      setEvidenceState();
      clearButton.disabled = false;
      await loadHistory();
      input.focus();
    } catch (error) {
      addMessage("assistant", formatClientError(error));
    }
  });
  clearButton.addEventListener("click", async () => {
    if (!conversationId || !window.confirm(uiLabels().clearConfirm)) return;
    try {
      await Satya.request(`/api/conversations/${conversationId}`, { method: "DELETE" });
      conversationId = null;
      messages.replaceChildren();
      const welcome = document.createElement("div");
      welcome.className = "chat-welcome";
      const hasVerifiedSources = knowledgeStatus?.dataset.available === "true";
      const labels = uiLabels();
      welcome.innerHTML = `<div class="welcome-symbol"><span class="welcome-symbol-inner"><i class="bi bi-stars"></i></span><span class="welcome-ring"></span></div><div class="welcome-eyebrow">${labels.clearedEyebrow}</div><h1>${labels.clearedTitleHtml}</h1><p>${hasVerifiedSources ? labels.welcomeReadyBody : labels.welcomeEmptyBody}</p>`;
      messages.append(welcome);
      setEvidenceState();
      clearButton.disabled = true;
      await loadHistory();
    } catch (error) {
      addMessage("assistant", formatClientError(error));
    }
  });

  document.getElementById("toggleSidebar").addEventListener("click", (event) => {
    const sidebar = document.getElementById("researchSidebar");
    const open = sidebar.classList.toggle("sidebar-open");
    event.currentTarget.setAttribute("aria-expanded", String(open));
  });
  document.getElementById("toggleEvidence").addEventListener("click", () => evidencePanel.classList.toggle("evidence-open"));
  document.getElementById("closeEvidence").addEventListener("click", () => evidencePanel.classList.remove("evidence-open"));
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      newButton.click();
    }
    if (event.key === "Escape") {
      document.getElementById("researchSidebar").classList.remove("sidebar-open");
      evidencePanel.classList.remove("evidence-open");
      document.getElementById("toggleSidebar").setAttribute("aria-expanded", "false");
    }
  });

  Satya.request("/api/knowledge/status").then(renderKnowledgeStatus).catch(() => {});

  loadHistory().then(() => {
    const requestedConversation = new URLSearchParams(window.location.search).get("conversation");
    if (requestedConversation && /^\d+$/.test(requestedConversation)) openConversation(requestedConversation);
    const initialQuestion = new URLSearchParams(window.location.search).get("q");
    if (initialQuestion && !requestedConversation) {
      input.value = initialQuestion.slice(0, 4000);
      input.focus();
    }
  });

  function renderKnowledgeStatus(status) {
    lastKnowledgeStatus = status;
    if (!knowledgeStatus) return;
    const labels = uiLabels();
    const available = status.available === true;
    knowledgeStatus.dataset.available = String(available);
    knowledgeStatus.replaceChildren();
    const indicator = document.createElement("span");
    knowledgeStatus.append(indicator);
    knowledgeStatus.append(
      document.createTextNode(
        available ? labels.knowledgeReady(status.verified_sources) : labels.knowledgeUnavailable
      )
    );
    knowledgeStatus.classList.toggle("knowledge-ready", available);
    syncComposerText();
  }
});
