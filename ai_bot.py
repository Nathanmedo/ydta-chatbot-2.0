# ai_bot.py
import os
import json
from typing import TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from vector import retrieve, fetch_data_from_db, init_vector_store, get_vector_store

topic_content = ""

class MyFormat(BaseModel):
    categoty: str = Field(..., description="question category, from context e.g Academics, Administrative, History")
    code: int = Field(..., description="set this as 1 if you have a definitive answer for the question and 0 if not")
    answer: str = Field(..., description="the assistant's response to the user")


class AgentState(TypedDict):
    messages: list[HumanMessage | AIMessage]
    currQuestion: str
    currAnswer: str
    cookie: list
    llm: ChatGoogleGenerativeAI
    category : str
    code: int
    

def create_agent_state() -> AgentState:
    """Initialize the agent's state with empty messages and loaded knowledge/JSON data."""
    return AgentState(
        messages=[],
        currQuestion="",
        currAnswer="",
        cookie=[],
        code=0,
        category=""
    )


def create_llm(api_key: str) -> ChatGoogleGenerativeAI:
    """Create and return a Google Generative AI model instance."""
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        max_output_tokens=1024,
        temperature=0.4,
        google_api_key=api_key
    )
    return model


def get_prompt_audit(state:AgentState) -> str:
    prompt = state["currQuestion"]
    df = fetch_data_from_db()
    store = get_vector_store()
    
    context = retrieve(prompt, store)
    print(context)
    
    SYSTEM_PROMPT = """

        You are the official virtual assistant for Yaba College of Technology (City University of Technology, Yaba).  
        Your purpose is to provide accurate, professional, and context-driven responses to students, applicants, and staff.  

        ### Core Rules
        1. **No Fabrication**  
        - Only answer using the provided context or trusted Yabatech information.  
        - If the answer is unavailable, respond with:  
            "I do not have that information. Please contact [relevant department] at [email/website]."

        2. **Scope of Knowledge**  
        - Limit responses to Yabatech-related topics: admissions, academics, deadlines, fees, exams, courses, student life, services, policies, and official procedures.  
        - If asked about unrelated topics, politely explain that you only provide Yabatech and school-related information.  


        ### Key Responsibilities
        - Provide timely details on **academic deadlines, registration, and fee payments**.  
        - Assist with **technical issues** (portal, password reset, email access) by guiding users to the correct channels.  
        - Share information on **course schedules, exam timetables, and graduation requirements**.  
        - Give guidance on **campus life, services, and official policies**.  
        - When referring users to other resources, **always provide clear next steps** (contact info, URLs, or forms).  

        ### Identity
        Always act as the official voice of Yaba College of Technology, representing the institution with authority and friendliness.  

    """
    FINAL_PROMPT = f"""{SYSTEM_PROMPT}
        Context (from knowledge base):
        {context}
        please always rephrase your answers to give the most welcoming human-like responses, extra words for very short questions are allowed as well
        Answer as the friendly assistant, continuing the flow if the conversation if any (Dont say unnecesary hellos):
    """
    
    return FINAL_PROMPT

def ask_question(state: AgentState) -> AgentState:
    """Invokes the language model with full conversation history."""

    FINAL_PROMPT = get_prompt_audit(state=state)
    messages_to_send = [HumanMessage(content=FINAL_PROMPT)]

    # Include conversation history
    for turn in state.get("cookie", []):
        messages_to_send.append(HumanMessage(content=turn["user"]))
        if turn.get("bot"):
            messages_to_send.append(AIMessage(content=turn["bot"]))

    structured = state["llm"].with_structured_output(MyFormat)
    try:
        response: MyFormat = structured.invoke(messages_to_send)
    except Exception as e:
        print("Structured output error:", e)
        fallback_text = state["llm"].invoke(messages_to_send).content
        response = MyFormat(category="Unknown", code=0, answer=fallback_text)

    bot_reply = response.answer
    code = response.code
    category = response.categoty

    state["currAnswer"] = bot_reply
    state["code"] = code
    state["category"] = category
    state["messages"] = messages_to_send + [AIMessage(content=bot_reply)]

    # Safely update last cookie
    if state["cookie"]:
        state["cookie"][-1]["bot"] = bot_reply
    else:
        state["cookie"].append({"user": state["currQuestion"], "bot": bot_reply})

    return state




def make_graph_and_compile(cookie:list, api_key: str):
    """Create nodes, add edges, compile the StateGraph, and run the flow."""
    graph = StateGraph(AgentState)
    graph.add_node("ask_question", ask_question)
    graph.add_edge("ask_question", END)
    graph.set_entry_point("ask_question")

    compiled_graph = graph.compile()

    state = create_agent_state()
    state['cookie'] = cookie
    state['currQuestion'] = cookie[-1]['user']
    state['llm'] = create_llm(api_key)

    final_state = compiled_graph.invoke(state)

    return {"response": final_state['currAnswer'],'code' : final_state['code'], 'category': final_state['category'] }

def get_response(user_message: str, chat_history: list, api_key: str) -> str:
    """
    Main function to get a response from the chatbot, maintaining a session.
    """
    chat_history.append({'user': user_message, 'bot': None})

    response_data = make_graph_and_compile(chat_history, api_key)

    chat_history[-1]['bot'] = response_data['response']

    return response_data['response'], chat_history, response_data["code"], response_data['category'] 


def guided_learning_response(topic: str, api_key: str) -> str:
    """
    Generates a structured, guided research plan for a course or topic.
    This function uses a separate, more dynamic prompt than the FAQ bot to act as a research assistant.
    """
    llm = create_llm(api_key)

    prompt = f"""
    Act as an expert learning guide for a Yabatech student. Your task is to generate a detailed, actionable, and hands-on learning plan for the following topic: {topic}.

Your response must be structured into three distinct sections, formatted with bold headings:

### **1. Key Concepts**
Provide a list of the most important ideas, principles, and vocabulary the student needs to understand for the given topic.

### **2. Practical Application / Hands-on Activity**
Outline a small, practical project, case study, or exercise. Include clear, step-by-step instructions for the student to follow.

### **3. Relevant Example or Demonstration**
Present a complete and well-commented example or a solution to a key component of the activity. If the topic is technical, provide a code snippet in a code block with the appropriate language tag. Otherwise, offer a clear, illustrative example for the field of study.

Ensure the final output is well-formatted using Markdown, including lists and bold headings as specified.
    """
    try:
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception as e:
        print(f"An error occurred: {e}")
        return "I'm sorry, I'm unable to generate a research plan at this time."


if __name__ == "__main__":
    response = get_response("who is the rector", [{"user": "who is the rector", 'bot' : ""}], "AIzaSyAMQJd9248W4eB_uw8p7BNLC3wq73RINp8")
    print(response)
    

    
