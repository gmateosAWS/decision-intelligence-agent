from langchain.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings

vectorstore = FAISS.load_local(
    "knowledge_index",
    OpenAIEmbeddings(),
    allow_dangerous_deserialization=True
)

def retrieve_knowledge(query):

    docs = vectorstore.similarity_search(query,k=2)

    return "\n".join([d.page_content for d in docs])