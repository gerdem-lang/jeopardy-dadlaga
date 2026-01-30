import streamlit as st
import pandas as pd
import random
from collections import defaultdict

# Page config
st.set_page_config(page_title="Jeopardy Game", layout="wide")

# Custom CSS for styling
st.markdown("""
<style>
    .category-header {
        text-align: center;
        font-size: 24px;
        font-weight: bold;
        padding: 10px;
        margin-bottom: 10px;
    }
    .stButton button {
        width: 100%;
        height: 80px;
        font-size: 24px;
        font-weight: bold;
    }
    .winner-text {
        text-align: center;
        font-size: 48px;
        font-weight: bold;
        color: #FFD700;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        padding: 30px;
        animation: pulse 1.5s ease-in-out infinite;
    }
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
    }
</style>
""", unsafe_allow_html=True)

# Load questions from CSV
@st.cache_data
def load_questions(csv_file="questionsanswers.csv"):
    """Load questions and organize by category and points"""
    # Try different encodings
    encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252']
    df = None
    
    for encoding in encodings:
        try:
            df = pd.read_csv(csv_file, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    
    if df is None:
        st.error(f"Could not read CSV file with any common encoding. Please save it as UTF-8.")
        st.stop()
    
    # Group questions by (category, points)
    question_pool = defaultdict(list)
    for _, row in df.iterrows():
        key = (row['category'], int(row['points']))
        question_pool[key].append({
            'question': row['question'],
            'answer': row['answer']
        })
    
    # Get unique categories and points
    categories = sorted(df['category'].unique())
    points = sorted(df['points'].unique())
    
    return question_pool, categories, points

def initialize_game():
    """Initialize or reset game state"""
    question_pool, categories, points = load_questions()
    
    # Randomly select one question per (category, points) slot
    board = {}
    for cat in categories:
        for pt in points:
            key = (cat, pt)
            if key in question_pool and question_pool[key]:
                board[key] = {
                    'question_data': random.choice(question_pool[key]),
                    'used': False,
                    'revealed': False
                }
    
    return board, categories, points

# Initialize session state
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
    st.session_state.teams = []
    st.session_state.scores = {}
    st.session_state.board = {}
    st.session_state.categories = []
    st.session_state.points = []
    st.session_state.selected_question = None
    st.session_state.show_answer = False
    st.session_state.show_question_modal = False
    st.session_state.game_over = False

# Title
st.title("Jeopardy Game")

# Setup phase - before game starts
if not st.session_state.game_started:
    st.header("Game Setup")
    
    # Number of teams
    num_teams = st.number_input("Number of teams (2-8)", min_value=2, max_value=8, value=2)
    
    # Team names
    team_names = []
    cols = st.columns(2)
    for i in range(num_teams):
        with cols[i % 2]:
            name = st.text_input(f"Team {i+1} name", value=f"Team {i+1}", key=f"team_{i}")
            team_names.append(name)
    
    # Start game button
    if st.button("Start Game", type="primary"):
        st.session_state.teams = team_names
        st.session_state.scores = {team: 0 for team in team_names}
        st.session_state.board, st.session_state.categories, st.session_state.points = initialize_game()
        st.session_state.game_started = True
        st.session_state.game_over = False
        st.rerun()

# Game phase - after game starts
else:
    # Sidebar - Scores and Controls
    with st.sidebar:
        st.header("Scores")
        sorted_scores = sorted(st.session_state.scores.items(), key=lambda x: x[1], reverse=True)
        for i, (team, score) in enumerate(sorted_scores, 1):
            st.metric(f"{i}. {team}", score)
        
        st.divider()
        
        # New game button
        if st.button("New Game (Random Questions)"):
            st.session_state.board, st.session_state.categories, st.session_state.points = initialize_game()
            st.session_state.scores = {team: 0 for team in st.session_state.teams}
            st.session_state.selected_question = None
            st.session_state.show_answer = False
            st.session_state.show_question_modal = False
            st.session_state.game_over = False
            st.rerun()
        
        # Reset button
        if st.button("End Game & Setup New Teams"):
            st.session_state.game_started = False
            st.session_state.selected_question = None
            st.session_state.show_answer = False
            st.session_state.show_question_modal = False
            st.session_state.game_over = False
            st.rerun()
    
    # Question Page (separate view when question is selected)
    if st.session_state.selected_question and st.session_state.show_question_modal:
        cat, point = st.session_state.selected_question
        question_data = st.session_state.board[st.session_state.selected_question]['question_data']
        
        # Show question page (hides the board)
        st.header(f"{cat} - {point} points")
        st.write("")
        st.write("")
        
        # Question box
        st.markdown(f"""
        <div style="
            background-color: #1e3a5f;
            padding: 40px;
            border-radius: 10px;
            font-size: 28px;
            text-align: center;
            margin: 20px 0;
        ">
            {question_data['question']}
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        st.write("")
        
        # Show answer button
        if not st.session_state.show_answer:
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button("Reveal Answer", type="primary", key="reveal_modal", use_container_width=True):
                    st.session_state.show_answer = True
                    st.rerun()
        else:
            # Answer box
            st.markdown(f"""
            <div style="
                background-color: #2d5016;
                padding: 30px;
                border-radius: 10px;
                font-size: 24px;
                text-align: center;
                margin: 20px 0;
            ">
                <strong>Answer:</strong> {question_data['answer']}
            </div>
            """, unsafe_allow_html=True)
            
            st.write("")
            st.write("")
            
            # Award points section
            st.subheader("Award points to:")
            cols = st.columns(len(st.session_state.teams) + 1)
            
            for i, team in enumerate(st.session_state.teams):
                with cols[i]:
                    if st.button(f"✓ {team}", key=f"award_{team}_modal", use_container_width=True):
                        st.session_state.scores[team] += point
                        st.session_state.board[st.session_state.selected_question]['used'] = True
                        st.session_state.selected_question = None
                        st.session_state.show_answer = False
                        st.session_state.show_question_modal = False
                        st.rerun()
            
            with cols[-1]:
                if st.button("Skip", key="skip_modal", use_container_width=True):
                    st.session_state.board[st.session_state.selected_question]['used'] = True
                    st.session_state.selected_question = None
                    st.session_state.show_answer = False
                    st.session_state.show_question_modal = False
                    st.rerun()
            
            st.write("")
            
            # Wrong answer (subtract points)
            st.subheader("Or deduct points from:")
            cols2 = st.columns(len(st.session_state.teams))
            for i, team in enumerate(st.session_state.teams):
                with cols2[i]:
                    if st.button(f"✗ {team}", key=f"deduct_{team}_modal", use_container_width=True):
                        st.session_state.scores[team] -= point
                        st.session_state.board[st.session_state.selected_question]['used'] = True
                        st.session_state.selected_question = None
                        st.session_state.show_answer = False
                        st.session_state.show_question_modal = False
                        st.rerun()
        
        # Don't show the board when question is active
    else:
        # Check if game is over
        all_used = all(cell['used'] for cell in st.session_state.board.values())
        
        if all_used and not st.session_state.game_over:
            # Trigger balloons and set game over flag
            st.balloons()
            st.session_state.game_over = True
        
        if all_used:
            # Show winner celebration
            winner = max(st.session_state.scores.items(), key=lambda x: x[1])
            
            st.markdown(f"""
            <div class="winner-text">
                🎉 Congratulations! 🎉<br>
                {winner[0]} WINS!<br>
                Final Score: {winner[1]} points
            </div>
            """, unsafe_allow_html=True)
            
            st.write("")
            st.write("")
            
            # Show all final scores
            st.subheader("Final Standings:")
            sorted_scores = sorted(st.session_state.scores.items(), key=lambda x: x[1], reverse=True)
            for i, (team, score) in enumerate(sorted_scores, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                st.markdown(f"### {medal} {team}: {score} points")
        else:
            # Main board (only shown when no question is selected and game not over)
            st.header("Game Board")
        
            # Display board as grid with centered categories
            # Header row with categories
            header_cols = st.columns(len(st.session_state.categories))
            for i, cat in enumerate(st.session_state.categories):
                with header_cols[i]:
                    st.markdown(f'<div class="category-header">{cat}</div>', unsafe_allow_html=True)
            
            # Point rows
            for point in st.session_state.points:
                cols = st.columns(len(st.session_state.categories))
                for i, cat in enumerate(st.session_state.categories):
                    with cols[i]:
                        key = (cat, point)
                        if key in st.session_state.board:
                            cell = st.session_state.board[key]
                            if cell['used']:
                                st.button("X", key=f"btn_{cat}_{point}", disabled=True, use_container_width=True)
                            else:
                                if st.button(f"{point}", key=f"btn_{cat}_{point}", use_container_width=True):
                                    st.session_state.selected_question = key
                                    st.session_state.show_answer = False
                                    st.session_state.show_question_modal = True
                                    st.rerun()