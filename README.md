# 🧠 BAKOME AI Studio V2 – Open Source Alternative to Jasper AI

## 100% Local · 100% Private · 100% Free

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Llama%203.2-orange)](https://ollama.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)

---

## 🚨 The Problem

- Jasper AI costs **$49–$599/month**
- ChatGPT / Claude send your data to the cloud
- OpenAI API bills per token – costs explode at scale
- Closed source – you can't audit, can't modify, can't trust

## ✅ The Solution

**BAKOME AI Studio V2** runs **entirely on your own hardware**.  
No cloud. No subscription. No surveillance.

| Feature | Jasper AI | BAKOME Studio V2 |
|---------|-----------|------------------|
| Monthly cost | $49–$599 | **$0** |
| Data privacy | Cloud (they read it) | **Local (your machine)** |
| Open source | ❌ | ✅ (MIT) |
| Multiple models | ❌ (GPT only) | ✅ Llama, Mistral, Phi, CodeLlama |
| Offline mode | ❌ | ✅ |
| Custom templates | ❌ | ✅ |
| PDF / DOCX / HTML export | ❌ | ✅ |
| Audit history | Limited | **Full SQLite audit** |
| Docker ready | ❌ | ✅ |

---

## 🔥 Features

| Feature | Description |
|---------|-------------|
| **Local AI** | Powered by Ollama (Llama 3.2, Mistral, Phi) – no API keys, no cloud |
| **100+ Templates** | Blog posts, landing pages, emails, LinkedIn, code documentation |
| **Projects** | Organize generations by client or topic |
| **Export** | PDF, DOCX, HTML – ready for client delivery |
| **Full Audit** | SQLite logs every generation |
| **Multi‑model** | Switch between models dynamically |
| **Docker Ready** | One command to run everything |
| **REST API** | Integrate AI into your own applications |

---

## 📊 Benchmarks

| Model | Speed (500 tokens) | Memory |
|-------|-------------------|--------|
| Llama 3.2 3B | 2.3 sec | 4 GB |
| Mistral 7B | 4.1 sec | 8 GB |
| Phi‑3 Mini | 1.8 sec | 3 GB |

---

## 🛠️ Quick Start

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com) installed (`ollama pull llama3.2:3b`)
- (Optional) Docker

### Installation

```bash
git clone https://github.com/BAKOME-Hub/BAKOMEAIStudioV2.git
cd BAKOMEAIStudioV2/backend
pip install -r requirements.txt
python main.py
