#!/usr/bin/env python3
# Licensed to You under the Apache License, Version 2.0

"""
RAG (Retrieval Augmented Generation) Tool for Agentic Integration Tests

Provides document search capabilities over Dell iDRAC and PowerEdge user guides.
Based on the RAG implementation from poweredge-agentic-ai but simplified for testing.
"""

import os
import re
from typing import List, Dict, Any, Optional
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import BaseTool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from pydantic import BaseModel, Field, ConfigDict
from chromadb.config import Settings


class RAGConfig(BaseModel):
    """Configuration for RAG tool."""
    pdf_folder: str = "./data/pdfs"
    chunk_size: int = 1500
    chunk_overlap: int = 300
    embedding_model: str = "all-mpnet-base-v2"
    collection_name: str = "idrac_documents"
    persist_directory: str = "./data/chroma_db"
    retriever_k: int = 8
    retriever_fetch_k: int = 16


class RAGSearchInput(BaseModel):
    """Input schema for RAG search."""
    query: str = Field(description="The search query or question to find relevant information in the documentation")


class RAGTool:
    """RAG tool for searching Dell iDRAC and PowerEdge documentation."""

    def __init__(self, config: RAGConfig, llm):
        """
        Initialize RAG tool.

        Args:
            config: RAG configuration
            llm: LangChain-compatible LLM instance
        """
        self.config = config
        self.llm = llm
        self.embeddings = None
        self.vectorstore = None
        self.qa_chain = None

    def initialize(self):
        """Initialize embeddings, vector store, and QA chain."""
        print("[RAG] Initializing RAG tool...")

        # Initialize embeddings
        print(f"[RAG] Loading embedding model: {self.config.embedding_model}")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=self.config.embedding_model
        )

        # Setup vector store
        self._setup_vectorstore()

        # Setup QA chain
        self._setup_qa_chain()

        print("[RAG] ✓ RAG tool initialized")

    def _setup_vectorstore(self):
        """Setup or load the vector store."""
        print("[RAG] Setting up vector store...")

        # Ensure persist directory exists
        os.makedirs(self.config.persist_directory, exist_ok=True)

        # Configure ChromaDB settings with telemetry disabled
        chroma_settings = Settings(
            anonymized_telemetry=False,
            allow_reset=True,
            is_persistent=True
        )

        # Initialize Chroma vector store with telemetry disabled
        self.vectorstore = Chroma(
            collection_name=self.config.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.config.persist_directory,
            client_settings=chroma_settings
        )

        # Check if we need to load PDFs
        existing_count = self.vectorstore._collection.count()

        if existing_count == 0:
            print("[RAG] Vector store is empty, loading PDFs...")
            self._load_pdfs()
        else:
            print(f"[RAG] Using existing vector store with {existing_count} documents")

    def _load_pdfs(self):
        """Load and index PDF files."""
        if not os.path.exists(self.config.pdf_folder):
            print(f"[RAG] Warning: PDF folder not found: {self.config.pdf_folder}")
            print("[RAG] Create the folder and add PDF user guides to enable RAG search")
            return

        pdf_files = list(Path(self.config.pdf_folder).glob("*.pdf"))

        if not pdf_files:
            print(f"[RAG] No PDF files found in {self.config.pdf_folder}")
            return

        print(f"[RAG] Loading {len(pdf_files)} PDF files...")

        documents = []
        for pdf_file in pdf_files:
            try:
                print(f"[RAG]   Loading {pdf_file.name}...")
                loader = PyPDFLoader(str(pdf_file))
                docs = loader.load()
                documents.extend(docs)
            except Exception as e:
                print(f"[RAG]   ✗ Error loading {pdf_file.name}: {e}")

        if not documents:
            print("[RAG] No documents loaded")
            return

        print(f"[RAG] Loaded {len(documents)} pages, splitting into chunks...")

        # Enhanced text splitter for Dell technical docs
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            separators=[
                "\n" + "="*50 + "\n",  # Section dividers
                "\n" + "-"*50 + "\n",
                "\n" + "_"*50 + "\n",
                "\n" + "="*20 + "\n",
                "\n" + "-"*20 + "\n",
                "\n" + "_"*20 + "\n",
                "\n\n\n",
                "\n\n",
                "\nTable ",
                "\nFigure ",
                "\nNote:",
                "\nCaution:",
                "\nWarning:",
                "\n",
                ". ",
                " ",
                ""
            ],
            keep_separator=True
        )

        chunks = text_splitter.split_documents(documents)

        # Enhance metadata
        for chunk in chunks:
            source_file = chunk.metadata.get("source", "")
            if source_file:
                filename_lower = source_file.lower()
                if "troubleshooting" in filename_lower or "fault" in filename_lower or "error" in filename_lower:
                    chunk.metadata["doc_type"] = "troubleshooting"
                elif "api" in filename_lower or "redfish" in filename_lower:
                    chunk.metadata["doc_type"] = "api_reference"
                elif "user" in filename_lower or "guide" in filename_lower:
                    chunk.metadata["doc_type"] = "user_guide"
                elif "admin" in filename_lower or "config" in filename_lower:
                    chunk.metadata["doc_type"] = "administration"
                else:
                    chunk.metadata["doc_type"] = "general"

        print(f"[RAG] Adding {len(chunks)} chunks to vector store (this may take a while)...")

        # Add in batches
        batch_size = 5000
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            self.vectorstore.add_documents(batch)
            print(f"[RAG]   Added batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")

        print(f"[RAG] ✓ Indexed {len(chunks)} chunks from {len(pdf_files)} PDFs")

    def _setup_qa_chain(self):
        """Setup the QA chain with custom prompt."""
        print("[RAG] Setting up QA chain...")

        # Custom prompt for Dell iDRAC/PowerEdge context
        template = """You are an expert assistant for Dell iDRAC and PowerEdge server management.
Use the following pieces of context from official Dell documentation to answer the question at the end.

When answering:
- Provide practical, actionable information
- Include specific steps or procedures when available
- Mention fault codes (MessageIDs) when relevant
- Cite configuration details or settings
- If you don't find the answer in the context, say so clearly

Context from Dell documentation:
{context}

Question: {question}

Helpful Answer:"""

        prompt = PromptTemplate(
            template=template,
            input_variables=["context", "question"]
        )

        # Create retriever with MMR for diversity
        self.retriever = self.vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": self.config.retriever_k,
                "fetch_k": self.config.retriever_fetch_k,
                "lambda_mult": 0.7
            }
        )

        # Create QA chain using modern LCEL (LangChain Expression Language)
        # This replaces the deprecated RetrievalQA.from_chain_type()
        def format_docs(docs):
            """Format retrieved documents into a single context string."""
            return "\n\n".join(doc.page_content for doc in docs)

        self.qa_chain = (
            {
                "context": self.retriever | format_docs,
                "question": RunnablePassthrough()
            }
            | prompt
            | self.llm
            | StrOutputParser()
        )

        # Store retriever for accessing source documents
        self.retriever_for_sources = self.retriever

        print("[RAG] ✓ QA chain ready")

    def _expand_query(self, query: str) -> str:
        """Expand query with Dell/PowerEdge synonyms for better retrieval."""
        synonyms = {
            "fault": ["error", "alert", "event", "message", "issue", "problem"],
            "recovery": ["resolution", "fix", "repair", "troubleshoot"],
            "cpu": ["processor", "CPU"],
            "memory": ["RAM", "DIMM", "memory module"],
            "power": ["PSU", "power supply"],
            "fan": ["cooling", "thermal"],
            "idrac": ["integrated Dell Remote Access Controller"],
            "bios": ["UEFI", "system setup"],
            "network": ["NIC", "ethernet", "network interface"],
            "storage": ["disk", "drive", "HDD", "SSD"],
        }

        expanded_terms = []
        query_lower = query.lower()

        for term, expansions in synonyms.items():
            if term in query_lower:
                expanded_terms.extend(expansions)

        if expanded_terms:
            return f"{query} {' '.join(expanded_terms)}"

        return query

    def query(self, question: str) -> Dict[str, Any]:
        """
        Query the RAG system.

        Args:
            question: The question to answer

        Returns:
            Dict with 'answer' and 'source_documents'
        """
        if not self.qa_chain:
            raise ValueError("RAG tool not initialized. Call initialize() first.")

        # Expand query for better retrieval
        expanded_question = self._expand_query(question)

        # Execute query with new LCEL chain (returns string directly)
        answer = self.qa_chain.invoke(expanded_question)

        # Retrieve source documents separately
        source_docs = self.retriever_for_sources.invoke(expanded_question)

        # Format response
        response = {
            "answer": answer,
            "source_documents": [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in source_docs
            ]
        }

        return response


class RAGSearchTool(BaseTool):
    """LangChain tool wrapper for RAG search."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "rag_search"
    description: str = (
        "Search through Dell iDRAC and PowerEdge documentation to find relevant information. "
        "Use this tool when you need to find specific information from user guides, "
        "answer questions about iDRAC features, troubleshooting guidance, or configuration details. "
        "This is particularly useful for finding fault recovery actions, understanding BIOS settings, "
        "or learning about Redfish API operations. "
        "Search with queries like 'how to configure BIOS boot order', 'fault CPU0001 recovery', "
        "or 'what is the Redfish endpoint for power control'."
    )
    args_schema: type[BaseModel] = RAGSearchInput

    rag_tool: RAGTool = Field(exclude=True)

    def __init__(self, rag_tool: RAGTool, **kwargs):
        super().__init__(rag_tool=rag_tool, **kwargs)

    def _run(self, query: str) -> str:
        """Execute RAG search."""
        try:
            result = self.rag_tool.query(query)

            # Format response with sources
            answer = result.get("answer", "No answer found")
            sources = result.get("source_documents", [])

            response = f"{answer}\n\n"

            if sources:
                response += "**Sources:**\n"
                for i, source in enumerate(sources[:4], 1):
                    content = source.get("content", "")
                    metadata = source.get("metadata", {})

                    source_file = metadata.get("source", "Unknown document")
                    page_num = metadata.get("page", "")

                    # Format filename
                    if source_file != "Unknown document":
                        source_name = source_file.split("/")[-1] if "/" in source_file else source_file
                        source_name = source_name.replace(".pdf", "").replace("_", " ").title()
                    else:
                        source_name = "Unknown Document"

                    # Create excerpt
                    excerpt = content[:300] if len(content) > 300 else content
                    if len(content) > 300:
                        last_period = excerpt.rfind('. ')
                        if last_period > 200:
                            excerpt = excerpt[:last_period + 1]
                        else:
                            excerpt += "..."

                    page_str = f", p.{page_num}" if page_num else ""
                    response += f"{i}. *{source_name}{page_str}*\n   {excerpt}\n\n"

            return response

        except Exception as e:
            return f"Error performing RAG search: {str(e)}"

    async def _arun(self, query: str) -> str:
        """Async version (calls sync version)."""
        return self._run(query)


def create_rag_tool(llm, config: Optional[RAGConfig] = None) -> RAGSearchTool:
    """
    Create and initialize a RAG search tool.

    Args:
        llm: LangChain-compatible LLM instance
        config: Optional RAG configuration (uses defaults if not provided)

    Returns:
        Initialized RAGSearchTool
    """
    if config is None:
        config = RAGConfig()

    rag = RAGTool(config=config, llm=llm)
    rag.initialize()

    return RAGSearchTool(rag_tool=rag)
