from langchain.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings
from langchain.docstore.document import Document

docs = [

Document(page_content="Profit equals revenue minus cost"),

Document(page_content="Revenue equals price times demand"),

Document(page_content="Demand depends on price and marketing"),

Document(page_content="Monte Carlo simulation estimates risk")
]

vectorstore = FAISS.from_documents(
    docs,
    OpenAIEmbeddings()
)

vectorstore.save_local("knowledge_index")

print("Knowledge index built")