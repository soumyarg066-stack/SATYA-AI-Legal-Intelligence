NO_DOCUMENTS_ANSWER = (
    "No verified legal source documents are available in the knowledge base yet. "
    "An administrator must review and verify uploaded sources before SATYA can answer from them."
)


def answer_question(_question):
    """Keep the chatbot explicit and non-generative until verified sources are available."""
    return {
        "answer": NO_DOCUMENTS_ANSWER,
        "citations": [],
        "sources": [],
        "verified": False,
    }
