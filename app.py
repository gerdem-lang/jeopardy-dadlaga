"""
Blackjack Streamlit app with casino-style layout and Supabase logging.

Design goals:
- Official casino-like look
- Starting screen as a centered "lobby card"
- Dealer at the center-top of the table during play
- Player seats as clean rails with clear info
- Action buttons grouped in a control panel near the top
- Split works for all same-rank pairs (A-A, K-K, Q-Q, etc.)
- Card total is shown inline next to the cards
"""

import streamlit as st
import random
import json
import os
from datetime import datetime

# Try supabase import (optional)
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except Exception:
    create_client = None
    Client = None
    SUPABASE_AVAILABLE = False

st.set_page_config(
    page_title="Blackjack Casino",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Constants ----------
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
CARD_VALUES = {
    "A": 11,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 10,
    "Q": 10,
    "K": 10,
}
STARTING_CHIPS = 1000
MIN_BET = 50

# ---------- Helpers (visual + Supabase + payouts) ----------


def display_card(rank, suit, hidden=False):
    """Return HTML for a single card (or a face-down card)."""
    if hidden:
        return (
            '<div style="'
            'display:inline-block;'
            'width:72px;height:104px;'
            'background:linear-gradient(135deg,#1f2937,#4b5563);'
            'border-radius:10px;margin:4px;'
            'box-shadow:0 6px 14px rgba(0,0,0,0.6);'
            '"></div>'
        )

    color = "red" if suit in ["♥", "♦"] else "black"
    return (
        '<div style="'
        'display:inline-block;'
        'width:72px;height:104px;'
        'background:white;border-radius:10px;'
        'margin:4px;text-align:center;'
        f'color:{color};'
        'font-weight:bold;'
        'font-size:24px;'
        'padding-top:10px;'
        'box-shadow:0 6px 14px rgba(0,0,0,0.5);'
        'border:1px solid #e5e7eb;'
        '">'
        f"{rank}<br/><span style=\"font-size:32px;\">{suit}</span></div>"
    )


def display_hand(cards, hide_second=False):
    html = ""
    for i, card in enumerate(cards):
        if hide_second and i == 1:
            html += display_card("", "", hidden=True)
        else:
            html += display_card(card[0], card[1])
    return html


def init_supabase_client():
    if not SUPABASE_AVAILABLE:
        return None

    url = None
    key = None
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
    except Exception:
        url = None
        key = None

    url = url or os.environ.get("SUPABASE_URL")
    key = key or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None

    try:
        client = create_client(url, key)
        return client
    except Exception:
        return None


def serializable_cards(cards):
    return [{"rank": r, "suit": s} for (r, s) in cards]


def save_round_to_supabase(supabase_client, dealer_hand, player_hands, bankrolls):
    """Save a snapshot of the round to Supabase."""
    if supabase_client is None:
        return False, "Supabase client not initialized."

    rows = []
    ts = datetime.utcnow().isoformat() + "Z"
    dealer_cards = serializable_cards(dealer_hand.cards)
    dealer_value = dealer_hand.get_value()

    for name, hands in player_hands.items():
        for idx, hand in enumerate(hands):
            player_cards = serializable_cards(hand.cards)
            bet = hand.bet
            pv = hand.get_value()

            if hand.is_bust:
                result = "bust"
                payout = 0
            elif hand.is_blackjack and not dealer_hand.is_blackjack:
                result = "blackjack"
                payout = int(bet * 2.5)
            elif dealer_hand.is_bust:
                result = "dealer_bust_win"
                payout = bet * 2
            elif pv > dealer_value:
                result = "win"
                payout = bet * 2
            elif pv == dealer_value:
                result = "push"
                payout = bet
            else:
                result = "lose"
                payout = 0

            rows.append(
                {
                    "ts": ts,
                    "player_name": name,
                    "hand_index": idx,
                    "bet": bet,
                    "result": result,
                    "payout": payout,
                    "final_bankroll": bankrolls.get(name),
                    "player_cards": json.dumps(player_cards),
                    "dealer_cards": json.dumps(dealer_cards),
                    "player_value": pv,
                    "dealer_value": dealer_value,
                }
            )

    try:
        res = supabase_client.table("rounds").insert(rows).execute()
        if hasattr(res, "error") and res.error:
            return False, f"Supabase insert error: {res.error}"
        if isinstance(res, dict) and res.get("error"):
            return False, f"Supabase insert error: {res['error']}"
        return True, "Saved round to Supabase."
    except Exception as e:
        return False, f"Exception when inserting to Supabase: {e}"


def apply_payouts():
    """
    Apply payouts to bankrolls once per round.

    Important: this uses the current hand.bet, which already reflects doubling.
    Example: start 1000, bet 100, double -> bet=200, bankroll=800.
    Win (non-blackjack): payout=bet*2=400, final bankroll=1200.
    """
    dealer_hand = st.session_state.dealer_hand
    dealer_value = dealer_hand.get_value()
    dealer_bust = dealer_hand.is_bust
    dealer_blackjack = dealer_hand.is_blackjack

    for name, hands in st.session_state.player_hands.items():
        for hand in hands:
            bet = hand.bet
            player_value = hand.get_value()

            if hand.is_bust:
                payout = 0
            elif hand.is_blackjack and not dealer_blackjack:
                payout = int(bet * 2.5)  # total returned (bet + profit)
            elif dealer_bust:
                payout = bet * 2
            elif player_value > dealer_value:
                payout = bet * 2
            elif player_value == dealer_value:
                payout = bet  # push returns bet
            else:
                payout = 0

            st.session_state.bankrolls[name] += payout

    st.session_state.payouts_applied = True


# ---------- Game core ----------


class Deck:
    def __init__(self, num_decks=6):
        self.num_decks = num_decks
        self._build()

    def _build(self):
        self.cards = []
        for _ in range(self.num_decks):
            for s in SUITS:
                for r in RANKS:
                    self.cards.append((r, s))
        random.shuffle(self.cards)

    def deal(self):
        if len(self.cards) == 0 or len(self.cards) < 15:
            self._build()
        return self.cards.pop()


class Hand:
    def __init__(self):
        self.cards = []
        self.bet = 0
        self.is_standing = False
        self.is_bust = False
        self.is_blackjack = False
        self.doubled = False

    def add_card(self, card):
        self.cards.append(card)
        self._update_states()
        # Auto-stand on 21
        if self.get_value() == 21:
            self.is_standing = True

    def _update_states(self):
        value = self.get_value()
        self.is_bust = value > 21
        self.is_blackjack = len(self.cards) == 2 and value == 21

    def get_value(self):
        value = 0
        aces = 0
        for rank, _ in self.cards:
            if rank == "A":
                aces += 1
                value += 11
            else:
                value += CARD_VALUES[rank]
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def can_split(self):
        """
        Can split ONLY when:
        - Exactly 2 cards
        - SAME RANK (A-A, K-K, Q-Q, J-J, 10-10, 9-9, etc.)
        """
        if len(self.cards) != 2:
            return False
        r1 = self.cards[0][0]
        r2 = self.cards[1][0]
        return r1 == r2

    def can_double(self):
        return len(self.cards) == 2 and not self.doubled


# ---------- Session state ----------

if "initialized" not in st.session_state:
    st.session_state.initialized = True

    # Game flow flags
    st.session_state.game_started = False
    st.session_state.betting_phase = True
    st.session_state.round_active = False
    st.session_state.dealer_turn = False
    st.session_state.round_over = False
    st.session_state.payouts_applied = False

    # Players & table
    st.session_state.num_players = 1
    st.session_state.player_names = []
    st.session_state.bankrolls = {}

    # Cards
    st.session_state.deck = None
    st.session_state.dealer_hand = None
    st.session_state.player_hands = {}
    st.session_state.current_player_idx = 0
    st.session_state.current_hand_idx = 0

    # Supabase
    st.session_state.supabase = init_supabase_client()

# ---------- Global CSS & Title ----------

st.markdown(
    """
<style>
    body {
        background: radial-gradient(circle at top, #111827 0, #020617 45%, #000 100%);
    }
    .main {
        background: radial-gradient(circle at 10% 20%, #052e16 0, #020617 55%, #020617 100%);
    }
    .app-header {
        text-align:center;
        margin-bottom:20px;
    }
    .app-title {
        font-size:40px;
        letter-spacing:0.25em;
        color:#e5e7eb;
        text-transform:uppercase;
        text-shadow:0 0 30px rgba(250,204,21,0.4),
                    0 0 60px rgba(250,204,21,0.25);
        margin-bottom:4px;
    }
    .app-subtitle {
        font-size:14px;
        color:#9ca3af;
        letter-spacing:0.22em;
        text-transform:uppercase;
    }

    .lobby-card {
        max-width:720px;
        margin:20px auto 40px auto;
        padding:26px 26px 30px 26px;
        border-radius:24px;
        background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(6,95,70,0.9));
        border:1px solid rgba(148,163,184,0.4);
        box-shadow:0 26px 40px rgba(0,0,0,0.7);
    }
    .lobby-card h2 {
        color:#f9fafb;
        margin-bottom:8px;
    }
    .lobby-card p {
        color:#9ca3af;
        margin-top:0;
        margin-bottom:16px;
        font-size:13px;
    }
    .lobby-section-label {
        font-size:13px;
        text-transform:uppercase;
        letter-spacing:0.15em;
        color:#9ca3af;
        margin-bottom:6px;
    }

    .casino-table {
        background: radial-gradient(circle, #064e3b 0%, #022c22 30%, #020617 80%);
        border-radius:40px;
        padding:28px 26px 34px 26px;
        margin:18px auto 16px auto;
        border:2px solid #4b5563;
        box-shadow:
            0 0 0 1px rgba(15,23,42,0.9),
            0 24px 55px rgba(0,0,0,0.85),
            inset 0 0 30px rgba(0,0,0,0.8);
    }

    .dealer-area {
        background: radial-gradient(circle at top, rgba(15,23,42,0.95) 0%, rgba(6,78,59,0.92) 55%, rgba(15,23,42,0.98) 100%);
        border-radius:24px;
        padding:22px 20px 22px 20px;
        text-align:center;
        border:1px solid rgba(148,163,184,0.6);
        box-shadow:0 18px 32px rgba(0,0,0,0.75);
        max-width:760px;
        margin:0 auto 20px auto;
        position:relative;
    }
    .dealer-badge {
        position:absolute;
        top:-14px;
        left:50%;
        transform:translateX(-50%);
        background:#facc15;
        color:#111827;
        padding:2px 14px 4px 14px;
        border-radius:999px;
        font-size:11px;
        font-weight:600;
        letter-spacing:0.16em;
        text-transform:uppercase;
        box-shadow:0 0 0 1px rgba(0,0,0,0.6);
    }

    .control-panel {
        background:rgba(15,23,42,0.96);
        border-radius:18px;
        padding:14px 16px 16px 16px;
        margin:0 auto 16px auto;
        border:1px solid rgba(148,163,184,0.5);
        max-width:880px;
        box-shadow:0 18px 26px rgba(0,0,0,0.7);
    }
    .control-panel-title {
        font-size:13px;
        text-transform:uppercase;
        letter-spacing:0.18em;
        color:#9ca3af;
        margin-bottom:4px;
    }
    .control-player-name {
        color:#f9fafb;
        font-size:18px;
        font-weight:600;
        margin-bottom:2px;
    }
    .control-meta {
        font-size:14px;
        color:#e5e7eb;
    }
    .control-meta-strong {
        font-size:22px;
        color:#f9fafb;
        font-weight:700;
        margin-top:4px;
    }
    .control-meta-small {
        font-size:12px;
        color:#9ca3af;
        margin-top:2px;
    }

    .player-row-title {
        text-align:center;
        margin:6px 0 10px 0;
        font-size:12px;
        letter-spacing:0.16em;
        text-transform:uppercase;
        color:#d1d5db;
    }

    /* player seats -> thin rail with glow on active */
    .player-seat {
        background:transparent;
        border-radius:0;
        padding:6px 4px 10px 4px;
        margin:4px 0;
        border:none;
        border-bottom:3px solid rgba(148,163,184,0.5);
        box-shadow:none;
        min-height:auto;
    }
    .player-seat-header {
        display:flex;
        align-items:center;
        justify-content:space-between;
        margin-bottom:4px;
    }
    .player-name {
        color:#e5e7eb;
        font-weight:600;
        font-size:15px;
    }
    .player-chips {
        color:#facc15;
        font-size:13px;
    }
    .player-seat-current {
        border-bottom:4px solid #facc15;
        box-shadow:0 4px 16px rgba(250,204,21,0.7);
        position:relative;
    }
    .player-seat-current::before {
        content:"CURRENT TURN";
        position:absolute;
        top:-12px;
        left:50%;
        transform:translateX(-50%);
        padding:1px 10px 2px 10px;
        border-radius:999px;
        background:#facc15;
        color:#111827;
        font-size:10px;
        font-weight:600;
        letter-spacing:0.16em;
        text-transform:uppercase;
        box-shadow:0 0 0 1px rgba(0,0,0,0.65);
    }

    .player-hand-tag {
        font-size:11px;
        color:#9ca3af;
        text-transform:uppercase;
        letter-spacing:0.13em;
        margin-bottom:2px;
    }
    .player-hand-value {
        font-size:20px;
        color:#f9fafb;
        margin-top:4px;
        font-weight:700;
    }
    .player-hand-status {
        font-size:12px;
        font-weight:600;
    }

    .result-card {
        background:rgba(15,23,42,0.96);
        border-radius:18px;
        padding:16px 18px;
        margin-bottom:14px;
        border:1px solid rgba(55,65,81,0.9);
        box-shadow:0 16px 26px rgba(0,0,0,0.8);
    }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="app-header">
  <div class="app-title">BLACKJACK CASINO</div>
  <div class="app-subtitle">DEAL · BET · WIN</div>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- Sidebar (Diagnostics + Cash Out + Restart) ----------

st.sidebar.header("Diagnostics")
supabase_client = getattr(st.session_state, "supabase", None)
st.sidebar.write(f"Supabase available: {SUPABASE_AVAILABLE}")
st.sidebar.write(f"Supabase initialized: {supabase_client is not None}")

st.sidebar.header("Table Controls")

if st.sidebar.button("Cash Out (show current stacks)"):
    bankrolls = getattr(st.session_state, "bankrolls", {})
    if bankrolls:
        st.sidebar.write("Current chip stacks:")
        for name, chips in bankrolls.items():
            st.sidebar.write(f"- {name}: {chips} chips")
    else:
        st.sidebar.write("No active bankrolls yet.")

if st.sidebar.button("Restart Table"):
    st.session_state.clear()
    st.rerun()

# ---------- SETUP PHASE (Starting) ----------

if not st.session_state.game_started:
    st.markdown('<div class="lobby-card">', unsafe_allow_html=True)
    st.markdown("### Table Setup", unsafe_allow_html=True)
    st.markdown(
        "<p>Configure the table before dealing the first hand.</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='lobby-section-label'>Players</div>",
        unsafe_allow_html=True,
    )
    num_players = st.slider(
        "Number of players",
        1,
        6,
        2,
        key="num_players_slider",
        label_visibility="collapsed",
    )

    player_names = []
    cols = st.columns(min(3, num_players))
    for i in range(num_players):
        with cols[i % 3]:
            name = st.text_input(
                f"Player {i+1}",
                value=f"Player {i+1}",
                key=f"name_{i}",
                label_visibility="visible",
            )
            player_names.append(name)

    st.markdown(
        "<div class='lobby-section-label'>Starting Stack</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p>Each player begins with <strong>{STARTING_CHIPS}</strong> chips.</p>",
        unsafe_allow_html=True,
    )

    start_col1, start_col2 = st.columns([1, 2])
    with start_col1:
        if st.button("Open Table", key="start_game", use_container_width=True):
            st.session_state.num_players = num_players
            st.session_state.player_names = player_names
            st.session_state.bankrolls = {
                name: STARTING_CHIPS for name in player_names
            }
            st.session_state.deck = Deck()
            st.session_state.game_started = True
            st.session_state.betting_phase = True
            st.session_state.dealer_hand = None
            st.session_state.player_hands = {}
            st.session_state.current_player_idx = 0
            st.session_state.current_hand_idx = 0
            st.session_state.payouts_applied = False
            st.rerun()
    with start_col2:
        st.caption("You can edit player names and seat count before opening the table.")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()
# ---------- BETTING PHASE ----------

if st.session_state.betting_phase and not st.session_state.round_active:
    st.markdown(
        "<div style='max-width:980px;margin:0 auto 16px auto;'>",
        unsafe_allow_html=True,
    )
    st.markdown("#### Betting Phase", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#9ca3af;font-size:13px;'>Set the wagers for this round. "
        "Minimum bet is 50 chips.</p>",
        unsafe_allow_html=True,
    )

    # Show bankrolls
    bank_cols = st.columns(len(st.session_state.player_names))
    for i, name in enumerate(st.session_state.player_names):
        with bank_cols[i]:
            chips = st.session_state.bankrolls.get(name, 0)
            st.markdown(
                f"""
                <div style="
                    background:rgba(15,23,42,0.96);
                    padding:10px 12px;border-radius:14px;
                    border:1px solid rgba(148,163,184,0.5);
                    text-align:center;
                    box-shadow:0 12px 20px rgba(0,0,0,0.7);
                    margin-bottom:6px;
                ">
                    <div style="color:#e5e7eb;font-weight:600;font-size:13px;">{name}</div>
                    <div style="color:#facc15;font-size:18px;font-weight:600;margin-top:2px;">
                        {chips} chips
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")
    bets = {}
    cols = st.columns(min(3, st.session_state.num_players))
    for i, name in enumerate(st.session_state.player_names):
        with cols[i % 3]:
            max_bet = st.session_state.bankrolls.get(name, 0)
            if max_bet < MIN_BET:
                st.info(f"{name}: insufficient chips to join this round.")
                bets[name] = 0
            else:
                default_bet = min(max_bet, max(MIN_BET, 100))
                bet = st.number_input(
                    f"{name} bet",
                    min_value=MIN_BET,
                    max_value=max_bet,
                    value=default_bet,
                    step=10,
                    key=f"bet_{name}",
                )
                bets[name] = bet

    st.write("")
    btn_col1, btn_col2 = st.columns([1, 3])
    with btn_col1:
        if st.button(
            "Deal Cards",
            key="deal",
            type="primary",
            use_container_width=True,
        ):
            if not any(b >= MIN_BET for b in bets.values()):
                st.warning("At least one player must place a bet of 50 or more.")
            else:
                st.session_state.dealer_hand = Hand()
                st.session_state.player_hands = {}
                st.session_state.deck = st.session_state.deck or Deck()

                for name, bet in bets.items():
                    if bet > 0:
                        hand = Hand()
                        hand.bet = bet
                        st.session_state.player_hands[name] = [hand]
                        st.session_state.bankrolls[name] -= bet

                # Deal initial cards: two to each player, two to dealer
                for _ in range(2):
                    for name in list(st.session_state.player_hands.keys()):
                        st.session_state.player_hands[name][0].add_card(
                            st.session_state.deck.deal()
                        )
                    st.session_state.dealer_hand.add_card(st.session_state.deck.deal())

                st.session_state.betting_phase = False
                st.session_state.round_active = True
                st.session_state.dealer_turn = False
                st.session_state.round_over = False
                st.session_state.payouts_applied = False
                st.session_state.current_player_idx = 0
                st.session_state.current_hand_idx = 0
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# ---------- PLAYING PHASE ----------

elif st.session_state.round_active and not st.session_state.round_over:
    st.markdown('<div class="casino-table">', unsafe_allow_html=True)

    # Dealer Area (center-top)
    st.markdown('<div class="dealer-area">', unsafe_allow_html=True)
    st.markdown('<div class="dealer-badge">DEALER</div>', unsafe_allow_html=True)

    if st.session_state.dealer_turn:
        st.markdown(
            f"<div style='display:flex;justify-content:center;'>{display_hand(st.session_state.dealer_hand.cards)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='color:#f9fafb;margin-top:8px;font-size:22px;font-weight:700;'>"
            f"Total: <span>{st.session_state.dealer_hand.get_value()}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='display:flex;justify-content:center;'>{display_hand(st.session_state.dealer_hand.cards, hide_second=True)}</div>",
            unsafe_allow_html=True,
        )
        upcard = (
            st.session_state.dealer_hand.cards[0][0]
            if st.session_state.dealer_hand
            and len(st.session_state.dealer_hand.cards) > 0
            else ""
        )
        st.markdown(
            f"<div style='color:#f9fafb;margin-top:8px;font-size:22px;font-weight:700;'>"
            f"Showing: <span>{upcard}</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # Control Panel (current player + actions + navigation)
    player_names = list(st.session_state.player_hands.keys())
    current_player_name = None
    current_hand = None

    if player_names and not st.session_state.dealer_turn:
        if 0 <= st.session_state.current_player_idx < len(player_names):
            current_player_name = player_names[st.session_state.current_player_idx]
            hands_list = st.session_state.player_hands[current_player_name]
            if 0 <= st.session_state.current_hand_idx < len(hands_list):
                current_hand = hands_list[st.session_state.current_hand_idx]

    st.markdown('<div class="control-panel">', unsafe_allow_html=True)
    st.markdown(
        '<div class="control-panel-title">Active Hand</div>',
        unsafe_allow_html=True,
    )

    if current_player_name and current_hand and not st.session_state.dealer_turn:
        playable = not current_hand.is_bust and not current_hand.is_standing

        c1, _ = st.columns([2, 3])
        with c1:
            st.markdown(
                f"<div class='control-player-name'>{current_player_name}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='control-meta'>Hand {st.session_state.current_hand_idx+1} "
                f"&nbsp;Â·&nbsp; Bet: {current_hand.bet} chips</div>",
                unsafe_allow_html=True,
            )

            # INLINE CARDS + TOTAL HERE
            st.markdown(
                f"""
                <div style="
                    display:flex;
                    align-items:center;
                    justify-content:flex-start;
                    gap:18px;
                    margin:10px 0 4px 0;
                ">
                    <div>{display_hand(current_hand.cards)}</div>
                    <div style="
                        font-size:26px;
                        font-weight:800;
                        color:#facc15;
                        padding-left:10px;
                    ">
                        TOTAL: {current_hand.get_value()}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Small helper text about split eligibility
            can_split_now = current_hand.can_split()
            bankroll_ok = (
                st.session_state.bankrolls[current_player_name] >= current_hand.bet
            )
            split_msg = (
                "Can split"
                if can_split_now and bankroll_ok and playable
                else "Cannot split (need same rank, 2 cards, and enough chips)"
            )
            st.markdown(
                f"<div class='control-meta-small'>{split_msg}</div>",
                unsafe_allow_html=True,
            )

        st.write("")

        # Action buttons row
        a1, a2, a3, a4 = st.columns(4)
        with a1:
            if st.button(
                "Hit",
                key="action_hit",
                use_container_width=True,
                disabled=not playable,
            ):
                if playable:
                    current_hand.add_card(st.session_state.deck.deal())
                st.rerun()
        with a2:
            if st.button(
                "Stand",
                key="action_stand",
                use_container_width=True,
                disabled=not playable,
            ):
                if playable:
                    current_hand.is_standing = True
                st.rerun()
        with a3:
            can_double = (
                playable
                and current_hand.can_double()
                and (
                    st.session_state.bankrolls[current_player_name]
                    >= current_hand.bet
                )
            )
            if st.button(
                "Double",
                key="action_double",
                disabled=not can_double,
                use_container_width=True,
            ):
                if can_double:
                    st.session_state.bankrolls[current_player_name] -= current_hand.bet
                    current_hand.bet *= 2
                    current_hand.doubled = True
                    current_hand.add_card(st.session_state.deck.deal())
                    current_hand.is_standing = True
                st.rerun()
        with a4:
            can_split = (
                playable
                and current_hand.can_split()
                and st.session_state.bankrolls[current_player_name]
                >= current_hand.bet
                and len(st.session_state.player_hands[current_player_name]) < 4
            )
            if st.button(
                "Split",
                key="action_split",
                disabled=not can_split,
                use_container_width=True,
            ):
                if can_split:
                    hands_list = st.session_state.player_hands[current_player_name]
                    new_hand = Hand()
                    new_hand.bet = current_hand.bet
                    second_card = current_hand.cards.pop()
                    new_hand.cards.append(second_card)
                    current_hand.add_card(st.session_state.deck.deal())
                    new_hand.add_card(st.session_state.deck.deal())
                    st.session_state.bankrolls[current_player_name] -= new_hand.bet
                    hands_list.insert(st.session_state.current_hand_idx + 1, new_hand)
                st.rerun()

        # ---------- TURN FLOW CONTROL (FORCED DEALER AFTER LAST PLAYER) ----------
        is_last_player = (
            st.session_state.current_player_idx == len(player_names) - 1
        )
        cur_name = player_names[st.session_state.current_player_idx]
        cur_hands = st.session_state.player_hands[cur_name]
        is_last_hand = (
            st.session_state.current_hand_idx == len(cur_hands) - 1
        )
        all_done = is_last_player and is_last_hand and (
            current_hand.is_bust or current_hand.is_standing
        )

        nav1, nav2 = st.columns(2)

        # PREVIOUS HAND (only if not first hand)
        with nav1:
            if st.button("Previous Hand", use_container_width=True):
                if st.session_state.current_hand_idx > 0:
                    st.session_state.current_hand_idx -= 1
                elif st.session_state.current_player_idx > 0:
                    st.session_state.current_player_idx -= 1
                    prev_name = player_names[st.session_state.current_player_idx]
                    st.session_state.current_hand_idx = (
                        len(st.session_state.player_hands[prev_name]) - 1
                    )
                st.rerun()

        # NEXT HAND OR FORCE DEALER
        with nav2:
            # Normal next hand / next player
            if not all_done:
                if st.button("Next Hand", use_container_width=True):
                    if not current_hand.is_standing and not current_hand.is_bust:
                        st.warning("You must Stand or Bust before moving on.")
                    else:
                        if st.session_state.current_hand_idx < len(cur_hands) - 1:
                            st.session_state.current_hand_idx += 1
                        elif st.session_state.current_player_idx < len(player_names) - 1:
                            st.session_state.current_player_idx += 1
                            st.session_state.current_hand_idx = 0
                        else:
                            # This case should be covered by all_done, but keep safe.
                            st.session_state.dealer_turn = True
                    st.rerun()
            # Last player, last hand, done â†’ only Reveal Dealer
            else:
                if st.button("Reveal Dealer", type="primary", use_container_width=True):
                    st.session_state.dealer_turn = True
                    while st.session_state.dealer_hand.get_value() < 17:
                        st.session_state.dealer_hand.add_card(
                            st.session_state.deck.deal()
                        )

                    if not st.session_state.payouts_applied:
                        apply_payouts()

                    st.session_state.round_over = True
                    st.rerun()

    else:
        # No active player hand (e.g. after everything is done, but before results)
        st.markdown(
            "<div style='color:#9ca3af;font-size:13px;'>"
            "All player actions complete. Reveal the dealer to resolve the round.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end control-panel

    # Players Area (seat rails) under control panel
    st.markdown(
        "<div class='player-row-title'>Table Seats</div>",
        unsafe_allow_html=True,
    )
    if player_names:
        seat_cols = st.columns(len(player_names))
        for idx, name in enumerate(player_names):
            with seat_cols[idx]:
                is_current = (
                    idx == st.session_state.current_player_idx
                    and not st.session_state.dealer_turn
                )
                seat_class = (
                    "player-seat player-seat-current" if is_current else "player-seat"
                )
                st.markdown(f'<div class="{seat_class}">', unsafe_allow_html=True)

                # Header
                st.markdown(
                    f"""
                    <div class="player-seat-header">
                      <div class="player-name">{name}</div>
                      <div class="player-chips">
                        {st.session_state.bankrolls.get(name, 0)} chips
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Hands (cards + inline TOTAL)
                hands = st.session_state.player_hands[name]
                for h_idx, hand in enumerate(hands):
                    st.markdown(
                        f"<div class='player-hand-tag'>Hand {h_idx+1} Â· Bet {hand.bet}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"""
                        <div style="
                            display:flex;
                            align-items:center;
                            justify-content:center;
                            gap:14px;
                            margin-top:4px;
                        ">
                            <div>{display_hand(hand.cards)}</div>
                            <div style="
                                font-size:22px;
                                font-weight:800;
                                color:#facc15;
                            ">
                                TOTAL: {hand.get_value()}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    status_text = ""
                    status_color = ""
                    if hand.is_bust:
                        status_text = "BUST"
                        status_color = "#f97373"
                    elif hand.is_blackjack:
                        status_text = "BLACKJACK"
                        status_color = "#22c55e"
                    elif hand.is_standing:
                        status_text = "Standing"
                        status_color = "#fbbf24"

                    if status_text:
                        st.markdown(
                            f"<div class='player-hand-status' "
                            f"style='color:{status_color};margin-top:2px;'>{status_text}</div>",
                            unsafe_allow_html=True,
                        )

                    if h_idx < len(hands) - 1:
                        st.markdown(
                            "<hr style='border-color:#4b5563;margin:6px 0;'>",
                            unsafe_allow_html=True,
                        )

                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)  # end casino-table
# ---------- RESULTS PHASE ----------

elif st.session_state.round_over:
    st.markdown(
        "<div style='max-width:980px;margin:8px auto 16px auto;'>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h3 style='text-align:left;color:#e5e7eb;'>Round Summary</h3>",
        unsafe_allow_html=True,
    )

    # Dealer final hand
    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    st.markdown(
        "<h4 style='color:#e5e7eb;margin-bottom:8px;'>Dealer Final Hand</h4>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='display:flex;justify-content:center;'>{display_hand(st.session_state.dealer_hand.cards)}</div>",
        unsafe_allow_html=True,
    )
    dealer_value = st.session_state.dealer_hand.get_value()
    st.markdown(
        f"<p style='color:#f9fafb;margin-top:8px;font-size:20px;font-weight:700;'>"
        f"Total: {dealer_value}</p>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # Player results (display only; bankrolls already updated in apply_payouts)
    for name, hands in st.session_state.player_hands.items():
        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.markdown(
            f"<h4 style='color:#facc15;margin-bottom:8px;'>{name}</h4>",
            unsafe_allow_html=True,
        )
        for idx, hand in enumerate(hands):
            pv = hand.get_value()
            bet = hand.bet

            if hand.is_bust:
                label = "BUST - LOSE"
                payout = 0
                color = "#f97373"
            elif hand.is_blackjack and not st.session_state.dealer_hand.is_blackjack:
                label = "BLACKJACK - WIN 3:2"
                payout = int(bet * 2.5)
                color = "#22c55e"
            elif st.session_state.dealer_hand.is_bust:
                label = "DEALER BUST - WIN"
                payout = bet * 2
                color = "#22c55e"
            elif pv > dealer_value:
                label = "WIN"
                payout = bet * 2
                color = "#22c55e"
            elif pv == dealer_value:
                label = "PUSH"
                payout = bet
                color = "#fbbf24"
            else:
                label = "LOSE"
                payout = 0
                color = "#f97373"

            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(
                    f"<p style='color:#9ca3af;font-size:13px;'>Hand {idx+1} Â· Bet {bet}</p>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='display:flex;justify-content:center;'>{display_hand(hand.cards)}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<p style='color:#f9fafb;font-size:20px;font-weight:700;'>"
                    f"Total: {pv}</p>",
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(
                    f"""
                    <div style="
                        background:rgba(15,23,42,0.96);
                        padding:10px 12px;border-radius:12px;
                        text-align:center;border:1px solid rgba(75,85,99,0.9);
                    ">
                        <div style="color:{color};font-weight:600;font-size:14px;margin-bottom:4px;">
                            {label}
                        </div>
                        <div style="color:#e5e7eb;font-size:13px;">
                            Payout: {payout}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown(
            f"<p style='color:#facc15;font-size:15px;margin-top:8px;'>"
            f"New bankroll: <strong>{st.session_state.bankrolls[name]} chips</strong></p>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Action buttons
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Save to Supabase", key="save_supabase", use_container_width=True):
            sup = getattr(st.session_state, "supabase", None)
            ok, msg = save_round_to_supabase(
                sup,
                st.session_state.dealer_hand,
                st.session_state.player_hands,
                st.session_state.bankrolls,
            )
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    with col2:
        if st.button(
            "Save and Next Round",
            key="save_and_next",
            type="primary",
            use_container_width=True,
        ):
            sup = getattr(st.session_state, "supabase", None)
            ok, msg = save_round_to_supabase(
                sup,
                st.session_state.dealer_hand,
                st.session_state.player_hands,
                st.session_state.bankrolls,
            )
            if not ok:
                st.error(msg)
            st.session_state.betting_phase = True
            st.session_state.round_active = False
            st.session_state.round_over = False
            st.session_state.dealer_turn = False
            st.session_state.payouts_applied = False
            st.session_state.dealer_hand = None
            st.session_state.player_hands = {}
            st.rerun()

    with col3:
        if st.button(
            "Next Round (no save)",
            key="next_no_save",
            use_container_width=True,
        ):
            st.session_state.betting_phase = True
            st.session_state.round_active = False
            st.session_state.round_over = False
            st.session_state.dealer_turn = False
            st.session_state.payouts_applied = False
            st.session_state.dealer_hand = None
            st.session_state.player_hands = {}
            st.rerun()

# ---------- Sidebar utilities (Supabase fetch) ----------

st.sidebar.header("Supabase")
if st.sidebar.button("Fetch Recent Rounds"):
    sup = getattr(st.session_state, "supabase", None)
    if sup is None:
        st.sidebar.write("Supabase not initialized.")
    else:
        try:
            resp = (
                sup.table("rounds")
                .select(
                    "id,ts,player_name,hand_index,bet,result,payout,final_bankroll"
                )
                .order("id", desc=True)
                .limit(20)
                .execute()
            )
            if hasattr(resp, "data"):
                st.sidebar.write(resp.data)
            elif isinstance(resp, dict) and resp.get("data"):
                st.sidebar.write(resp["data"])
            else:
                st.sidebar.write(resp)
        except Exception as e:
            st.sidebar.write(f"Supabase query error: {e}")