# Recall App

**An AI-assisted active-recall application for retaining what you learn.**

Recall App turns personal study notes into scheduled retrieval practice. Add reference material, create focused questions, explain answers from memory, review AI feedback, and schedule the next review with FSRS.

The goal is to support durable understanding—not simply store notes or generate conventional front/back flashcards.

## Features

- **Reference library:** Organize learning material into topics.
- **Question generation:** Generate focused review questions and expected key points from approved notes.
- **Free-form recall:** Answer in your own words without seeing the reference.
- **Structured feedback:** Identify correct points, omissions, incorrect claims, and unverified additions.
- **Duplicate detection:** Retrieve potentially overlapping questions with SQLite FTS5 and assess semantic similarity with an LLM.
- **Spaced repetition:** Schedule each review item independently using FSRS.
- **Human-controlled ratings:** Review and confirm the suggested rating before scheduling changes.
- **Review history:** Keep a record of attempts, feedback, and scheduling decisions.

## How It Works

1. Add a topic and its reference notes.
2. Generate or write focused review questions.
3. Edit and approve each question and its expected key points.
4. When a question is due, answer it from memory.
5. Compare the answer with the approved reference and rubric.
6. Review the feedback and confirm a rating.
7. FSRS calculates the next review date.

```text
Reference notes
      |
      v
Review questions + expected key points
      |
      v
Scheduled recall
      |
      v
Free-form answer
      |
      v
AI feedback against the reference
      |
      v
User-confirmed rating
      |
      v
FSRS schedules the next review
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3, TypeScript, Vite |
| Backend | Python, FastAPI |
| Database | SQLite |
| Data models and validation | SQLModel, Pydantic |
| Spaced repetition | Py-FSRS |
| AI integration | OpenAI API with structured outputs |
| Candidate retrieval | SQLite FTS5 |

## Getting Started

### Prerequisites

Install the following before running the application:

- Python
- Node.js and npm
- An OpenAI API key

### 1. Get the source code

```bash
git clone https://github.com/lovepreet223/Recall-App.git
cd Recall-App
```

### 2. Set up the backend

Open a terminal in the backend directory:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment.

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**

```bat
.venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

Install the backend dependencies:

```bash
pip install -r requirements.txt
```

Configure the environment variables using the names documented by the backend's `.env.example` file. At minimum, provide the OpenAI API key if AI features are enabled.

### 3. Start the backend

From the backend directory, start the FastAPI application using the project's configured ASGI entry point:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Once running, the API is typically available at:

```text
http://127.0.0.1:8000
```

### 4. Set up the frontend

Open a second terminal:

```bash
cd frontend
npm install
```

Start the Vite development server:

```bash
npm run dev
```

Open the local URL printed in the terminal (Vite commonly uses `http://localhost:5173`).

### 5. Use the application

1. Create a topic and add reference notes.
2. Generate or manually add review questions.
3. Review questions when they appear in the due queue.
4. Submit an explanation from memory.
5. Read the feedback and confirm your review rating.

## Architecture

The application is a local-first web application:

- The Vue frontend communicates with the FastAPI backend.
- SQLite stores topics, reference material, review items, attempts, feedback, and scheduling state.
- Py-FSRS calculates review intervals from user-confirmed ratings.
- The OpenAI API generates questions and evaluates submitted answers.
- SQLite FTS5 retrieves likely-related questions before the semantic duplicate check.

For answer evaluation, the model receives the relevant question, approved reference, expected key points, and submitted answer—not the entire learning library.

Only AI-related requests are sent to the external model API. Local application data is stored in SQLite.

## Important Design Choices

### Free-form answers

Reviews ask users to explain concepts rather than only recognize a correct option. This supports assessment of explanations, relationships, and conceptual understanding.

### Review individual concepts

A topic can contain multiple review items, each with its own scheduling state. Forgetting one concept does not automatically reschedule every item in the topic.

### Treat AI feedback as assistance

The evaluator compares an answer with the saved reference and expected key points. Information not covered by the reference is identified as unverified rather than automatically marked wrong.

AI feedback can still be mistaken. The user reviews the feedback and confirms or changes the suggested rating before FSRS is updated.

## Project Status

The project is in active development. The core workflow covers reference management, question generation, free-form recall, structured feedback, user-confirmed ratings, and FSRS scheduling.


## Limitations

- AI evaluation can misjudge correct explanations or accept incorrect ones.
- Feedback quality depends on the accuracy and completeness of the saved reference.
- FTS5 candidate retrieval can miss semantically similar questions that use different terminology.
- The evaluator does not currently execute code, verify mathematical derivations, or independently fact-check answers against authoritative sources.
- The current design targets a single local user; authentication, multi-user support, and cloud synchronization are not included.

## Roadmap

- Build a manually labelled benchmark for evaluating AI grading reliability.
- Improve support for mathematical notation and equations.
- Explore local-model support for answer evaluation.
- Add progress views that highlight recurring knowledge gaps.
- Add interleaved questions for distinguishing related concepts.
- Explore PDF, image, and voice input.
