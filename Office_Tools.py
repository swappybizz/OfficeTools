import streamlit as st
from pymongo import MongoClient
import fitz  # PyMuPDF
import docx
from datetime import datetime
import base64
import uuid
import random
import json
from openai import OpenAI
MONGO_URI = st.secrets["mongo_uri"]
client = MongoClient(MONGO_URI)
db = client["OfficeTools"]
agents_collection = db["agents"]
documents_collection = db["documents"]
chat_history_collection = db["client_chat_history"] # each session is a single document
instruct_enquiry_store = db["instruct_enquiry_store"]


welcome_messages = [
    "Hello! How can I help you today?",
    "Hi there! What can I do for you?",
    "Hey, Lets get started! What do you need help with?",
    "Hello! How can be of service to you today?",
    "Let's get started! What do you need help with?"
]









def get_content(file):
    if file.name.endswith(".pdf"):
        doc = fitz.open(stream=file.read(), filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        file_type = "pdf"
    elif file.name.endswith(".docx"):
        doc = docx.Document(file)
        text = ""
        for para in doc.paragraphs:
            text += para.text
        file_type = "docx"
    else:
        text = base64.b64encode(file.read()).decode("utf-8")
        file_type = "other"
    return text, file_type
def get_all_agents():
    return agents_collection.find({})

def get_documents_by_agent(agent_id):
    documents = documents_collection.find({"agent_id": agent_id})
    contents = [doc["content"] for doc in documents]
    return contents

def fetch_reply(user_message, selected_agent, chat_history, agent_docs):
    # print(selected_agent["appended_kb"])
    special_instructions = f"""
    You are having a conversation with the USER on behalf of the INSTRUCTOR. 
    Your job is to follow the instructions provided, and converse with the user.
    Your responsibility, and charecterstics will be defined in your instructions. Stick to your charector.
    You will exclusively use the KNOWLEGE BASE to answer the USER's questions, and respond to the user's queries.
    If any information is unavailable in the KNOWLEDGE BASE, you will inform the user that the information is not available and ask the instructor to provide the information.
    You will let user know of your actions. You need not ask permission for this. Simply notify them and move on.
    You may also contact the instructor for notification, clasrity and confirmation on reasonable assumptions with respect to conversation and user.
    ###
    AIM: {selected_agent["userTitle"]}
    INSTRUCTIONS: {selected_agent["instructions"]}
    KNOWLEDGE BASE: 
    {agent_docs}
    OTHER INFO:
    {selected_agent["appended_kb"]}
    CONVERSATION HISTORY:
    {chat_history}
    RESPOND TO THIS:
    {user_message}
    ###
    You will use the following JSON schema:
    ***
    {{
        "response": {{
            "reply_to_user": "Your response to the user's last message".
            "further_action": null or {{
                "instructor_query": "Your query to the instructor, if information not available in the KNOWLEDGE BASE.",
            }}
        }}
    }}
    ***
    Do not repeat your response to the users or the queries to the instructor.
    Your reply_to_the_user will be a assertion, comment, clarification, validating statment, always follwed by a question.
    further_actions are optional, can be of Null or a instructor_query.
    You will only repond with valid JSON, add no further information or anythig else.
    """
    print(special_instructions)
    client = OpenAI(api_key=st.secrets["openai_api_key"])
    completion = client.chat.completions.create(
        model="gpt-4o",
        response_format = {"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": "You are an intermediate connector between a user and an instructor. You represent the instructor in a conversation. You can communcate with both the user and the instructor. You only respond in valid JSON",
            },
            {"role": "user", "content": special_instructions},
        ],
    )
    res = completion.choices[0].message.content
    response = json.loads(res)
    # get "reply_to_user" and "further_action" from response
    reply_to_user = response["response"]["reply_to_user"]
    further_action = response["response"]["further_action"]
    # add the reply to the chat history
    chat_history.append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": {
                "role": "assistant",
                "message": reply_to_user,
            },
        }
    )
    # add it to the db
    chat_history_collection.update_one(
        {"session_id": st.session_state.client_session_id},
        {
            "$push": {
                "chat": {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "role": "assistant",
                    "message": reply_to_user,
                }
            }
        },
        upsert=True,
    )
    # if further_action is not None, add to instruct_enquiry_store
    if further_action:
        instruct_enquiry_store.insert_one(
            {
                "session_id": st.session_state.client_session_id,
                "agent_id": selected_agent["_id"],
                "further_action": further_action,
                "reply_status": "pending",
                "reply": "",
            }
        )
        
    
st.set_page_config(
    page_title="Office Assistance Tools",
    page_icon=":office:",
    layout="wide",
    initial_sidebar_state="auto",
)

if "selected_agent" not in st.session_state:
    st.session_state.selected_agent = None

if "client_session_id" not in st.session_state:
    st.session_state.client_session_id = str(uuid.uuid4())

if "client_chat_history" not in st.session_state:
    st.session_state.client_chat_history = []
    
    st.session_state.client_chat_history.append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": {
                "role": "assistant",
                "message": random.choice(welcome_messages),
            },
        }
    )
        




tab1, tab2 = st.tabs(["ToolBox", "QueryBoard"])
with st.sidebar:
    st.title("Office Bots")
    agents = get_all_agents()
    with st.container(border=False, height=700):
        for idx, agent in enumerate(agents):
            with st.container(border=True):
                agentcol1, agentcol2 = st.columns(
                    [4,1]
                )
                with agentcol1:
                    st.markdown(agent["name"])
                with agentcol2:
                    if st.button(
                        "↗", key=f"pick_{agent['_id']}", use_container_width=True
                    ):
                        st.session_state.selected_agent = agent
                # st.divider()
                # st.write(agent["userTitle"])
                f"For Help in:"
                f" :red[{agent['userTitle']}]"
                        
with tab1:
    if st.session_state.selected_agent:
        with st.container(height=800, border= False):
            with st.container(height=650):
                for message in st.session_state.client_chat_history:
                    with st.chat_message(message["content"]["role"]):
                        st.write(message["content"]["message"])
            if prompt := st.chat_input("What is up?"):
                st.session_state.client_chat_history.append(
                    {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "content": {
                            "role": "user",
                            "message": prompt,
                        },
                    }
                )
                chat_history_collection.update_one(
                    {"session_id": st.session_state.client_session_id},
                    {
                        "$push": {
                            "chat": {
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "role": "user",
                                "message": prompt,
                            }
                        }
                    },
                    upsert=True,
                )
                agent_docs = get_documents_by_agent(st.session_state.selected_agent["_id"])
                fetch_reply(
                    user_message=prompt,
                    selected_agent=st.session_state.selected_agent,
                    chat_history=st.session_state.client_chat_history,
                    agent_docs=agent_docs
                )
                st.rerun()
            
with tab2:
    # add the queries that isntuctor has answered
    all_user_agent_instructor_queries = instruct_enquiry_store.find({})
    # if answered just show them here like a notice board
    for query in all_user_agent_instructor_queries:
        if query["reply_status"] == "replied":
            with st.container(border=True):
                f"""
                ####  :red[{query["further_action"]["instructor_query"]}]
                ## {query["reply"]}
                
                """
    
    pass
            


# NOTES:
# structure of query given to the instructor:
#                 {
#                 "session_id": st.session_state.client_session_id,
#                 "agent_id": selected_agent["_id"],
#                 "further_action": further_action,
#                 "reply_status": "pending" or "replied",
#                 "reply": "",
#             }
