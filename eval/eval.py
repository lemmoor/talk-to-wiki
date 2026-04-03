import logging, os, json
from dotenv import load_dotenv
from supabase import create_client
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Literal
import httpx

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

openai_client = OpenAI()


class EvalAnswer(BaseModel):
    rating_1_to_5: Literal[1, 2, 3, 4, 5] = Field(
        description="1=wrong/irrelevant, 2=mostly wrong, 3=partially correct or key details wrong, 4=correct but less specific than reference, 5=fully correct and specific"
    )
    rating_justification: str = Field(description="Brief explanation of the rating")


def evaluate(rag=False):
    eval_prompt = """
You are a strict evaluator for a Stardew Valley QA system.

Rate the answer on a 1-5 scale:

5 = Fully correct AND equally or more specific than the reference answer
4 = Correct and useful, but less specific (e.g. "in the mines" when the 
    reference says "levels 40-79 of the mines") — no wrong information
3 = Partially correct — gets the gist but missing important details, 
    or correct on some points but wrong on others
2 = Mostly wrong, but contains a grain of relevant truth
1 = Completely wrong, irrelevant, or nonsensical

Key guidelines:
- An answer can be CORRECT without being SPECIFIC. "The mines" is not 
  wrong — it's just vague. That's a 4, not a 3.
- A 3 requires actual errors or major omissions that would mislead the player.
- Rewording or paraphrasing is fine. Judge meaning, not phrasing.
- If the answer includes extra correct information beyond the reference, 
  that's still a 5.
- Don't penalize too harshly lack of information that wasn't asked for, but is in the reference answer. (e.g. question about parsnip sell price, but reference answer also includes where to buy seeds)"""

    with open("questions.json", "r") as f:
        questions = json.load(f)

    evaluated_questions = []

    for i, q in enumerate(questions):
        print(f"Evaluating question: {i+1}/{len(questions)}")

        response = ""
        if rag:
            try:
                r = httpx.post(
                    "http://localhost:8000/ask",
                    json={"query": q["question"]},
                    timeout=120,
                )
                r.raise_for_status()
                response = r.json()["response"]
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"HTTP error occurred for question: {q['question']}. Status code: {e.response.status_code}, Response content: {e.response.text}"
                )
                response = "Error: Failed to get response from RAG system."
                continue
        else:
            chat_response = openai_client.responses.create(
                model="gpt-5-nano",
                input="You are a helpful assistant for answering questions about the game Stardew Valley (without any mods, PC version). Answer the following question to the best of you ability without asking any follow-up questions: "
                + q["question"],
                reasoning={"effort": "low"},
            )
            response = chat_response.output_text

        # i have free tokens so I will use them xD
        eval_response = openai_client.responses.parse(
            model="gpt-5.4",
            instructions=eval_prompt,
            input=f"QUESTION: {q['question']}\n\nANSWER: {response}\n\nCORRECT ANSWER: {q['answer']}",
            text_format=EvalAnswer,
            reasoning={"effort": "medium"},
        )

        result = eval_response.output_parsed

        if not result:
            logger.error(
                f"Failed to parse evaluation response for question: {q['question']}. Raw response: {eval_response.output_text}"
            )
            continue

        evaluated_questions.append(
            {
                "question": q["question"],
                "answer": response,
                "reference_answer": q["answer"],
                "rating": result.rating_1_to_5,
                "justification": result.rating_justification,
            }
        )

    with open(
        f"outputs/{'rag' if rag else 'non-rag'}_v3.json",
        "w",
    ) as f:
        json.dump(evaluated_questions, f, indent=2)


evaluate(rag=False)
evaluate(rag=True)
