import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sqlite3
import os
import numpy as np
from functools import reduce
import operator
import json

# Initialize database with enhanced tables and handle schema migration
def init_db():
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    
    # Check if old schema exists and migrate if needed
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bets'")
    table_exists = c.fetchone()
    
    if table_exists:
        # Check if new columns exist in old schema
        c.execute("PRAGMA table_info(bets)")
        columns = [column[1] for column in c.fetchall()]
        existing_columns = set(columns)
        
        # Add new columns if they don't exist
        new_columns = {
            'team_a': 'TEXT',
            'team_b': 'TEXT', 
            'bet_type': 'TEXT',
            'sport': 'TEXT',
            'is_parlay': 'INTEGER',
            'parlay_legs': 'TEXT'
        }
        
        for column_name, column_type in new_columns.items():
            if column_name not in existing_columns:
                c.execute(f"ALTER TABLE bets ADD COLUMN {column_name} {column_type}")
    
    else:
        # Create new enhanced bets table
        c.execute('''CREATE TABLE IF NOT EXISTS bets
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      date TEXT, team_a TEXT, team_b TEXT, 
                      bet_type TEXT, sport TEXT, stake REAL, 
                      odds REAL, result TEXT, profit_loss REAL, 
                      notes TEXT, is_parlay INTEGER, parlay_legs TEXT)''')
    
    # Quotes table
    c.execute('''CREATE TABLE IF NOT EXISTS quotes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT, quote_text TEXT,
                  category TEXT)''')
    
    # Bankroll table
    c.execute('''CREATE TABLE IF NOT EXISTS bankroll
                 (id INTEGER PRIMARY KEY, balance REAL)''')
    
    # Initialize bankroll if not exists (starting at 0 euros)
    c.execute('INSERT OR IGNORE INTO bankroll (id, balance) VALUES (1, 0)')
    
    conn.commit()
    conn.close()

# Enhanced add bet function with parlay support
def add_bet(date, team_a, team_b, bet_type, sport, stake, odds, result, notes="", is_parlay=False, parlay_legs=None):
    errors = validate_bet_input(stake, odds, result)
    if errors:
        raise ValueError("; ".join(errors))
    
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    
    # Calculate profit/loss
    profit_loss = calculate_profit_loss(stake, odds, result)
    
    # Convert parlay_legs to JSON string if it's a list
    parlay_legs_str = None
    if parlay_legs and isinstance(parlay_legs, list):
        parlay_legs_str = json.dumps(parlay_legs)
    
    c.execute('''INSERT INTO bets (date, team_a, team_b, bet_type, sport, stake, odds, result, profit_loss, notes, is_parlay, parlay_legs)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (date, team_a, team_b, bet_type, sport, stake, odds, result, profit_loss, notes, 1 if is_parlay else 0, parlay_legs_str))
    
    conn.commit()
    conn.close()

# Update bet function
def update_bet(bet_id, date, team_a, team_b, bet_type, sport, stake, odds, result, notes="", is_parlay=False, parlay_legs=None):
    errors = validate_bet_input(stake, odds, result)
    if errors:
        raise ValueError("; ".join(errors))
    
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    
    # Calculate profit/loss
    profit_loss = calculate_profit_loss(stake, odds, result)
    
    # Convert parlay_legs to JSON string if it's a list
    parlay_legs_str = None
    if parlay_legs and isinstance(parlay_legs, list):
        parlay_legs_str = json.dumps(parlay_legs)
    
    c.execute('''UPDATE bets 
                 SET date=?, team_a=?, team_b=?, bet_type=?, sport=?, stake=?, odds=?, result=?, profit_loss=?, notes=?, is_parlay=?, parlay_legs=?
                 WHERE id=?''',
              (date, team_a, team_b, bet_type, sport, stake, odds, result, profit_loss, notes, 1 if is_parlay else 0, parlay_legs_str, bet_id))
    
    conn.commit()
    conn.close()

# Calculate profit/loss
def calculate_profit_loss(stake, odds, result):
    if result == "Win":
        return (stake * odds) - stake
    elif result == "Loss":
        return -stake
    else:  # Push/Refund
        return 0

# Get single bet by ID
def get_bet_by_id(bet_id):
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    c.execute('SELECT * FROM bets WHERE id = ?', (bet_id,))
    bet = c.fetchone()
    conn.close()
    
    if bet:
        columns = ['id', 'date', 'team_a', 'team_b', 'bet_type', 'sport', 'stake', 'odds', 'result', 'profit_loss', 'notes', 'is_parlay', 'parlay_legs']
        return dict(zip(columns, bet))
    return None

# Calculate parlay odds from individual legs
def calculate_parlay_odds(legs):
    """Calculate combined odds for a parlay bet"""
    if not legs:
        return 1.0
    
    # Multiply all decimal odds together
    combined_odds = reduce(operator.mul, [leg['odds'] for leg in legs], 1.0)
    return round(combined_odds, 2)

# Input validation
def validate_bet_input(stake, odds, result):
    errors = []
    if stake <= 0:
        errors.append("Stake must be positive")
    if odds < 1.0:
        errors.append("Odds must be at least 1.0")
    if result not in ["Pending", "Win", "Loss", "Push"]:
        errors.append("Invalid result")
    return errors

# Add a quote
def add_quote(quote_text, category="Motivation"):
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    
    c.execute('''INSERT INTO quotes (timestamp, quote_text, category)
                 VALUES (?, ?, ?)''',
              (datetime.now().isoformat(), quote_text, category))
    
    conn.commit()
    conn.close()

# Get all bets with safe column handling
def get_bets():
    conn = sqlite3.connect('soccer_betting.db')
    df = pd.read_sql('SELECT * FROM bets ORDER BY date DESC', conn)
    conn.close()
    
    # Ensure all expected columns exist (for backward compatibility)
    expected_columns = ['id', 'date', 'team_a', 'team_b', 'bet_type', 'sport', 'stake', 'odds', 'result', 'profit_loss', 'notes', 'is_parlay', 'parlay_legs']
    for col in expected_columns:
        if col not in df.columns:
            if col in ['team_a', 'team_b', 'bet_type', 'sport', 'notes', 'parlay_legs']:
                df[col] = ""
            elif col == 'is_parlay':
                df[col] = 0
            else:
                df[col] = 0.0
    
    return df

# Get all quotes
def get_quotes():
    conn = sqlite3.connect('soccer_betting.db')
    df = pd.read_sql('SELECT * FROM quotes ORDER BY timestamp DESC', conn)
    conn.close()
    return df

# Calculate basic metrics
def calculate_metrics(df):
    if df.empty:
        return 0, 0, 0, 0
    
    total_pl = df['profit_loss'].sum()
    total_stake = df['stake'].sum()
    roi = (total_pl / total_stake * 100) if total_stake > 0 else 0
    win_rate = (df['result'] == 'Win').mean() * 100
    
    return total_pl, roi, win_rate, len(df)

# Calculate advanced metrics
def calculate_advanced_metrics(df):
    if df.empty:
        return {}
    
    settled_bets = df[df['result'].isin(['Win', 'Loss'])]
    if settled_bets.empty:
        return {}
    
    wins = settled_bets[settled_bets['result'] == 'Win']
    losses = settled_bets[settled_bets['result'] == 'Loss']
    
    avg_odds_win = wins['odds'].mean() if not wins.empty else 0
    avg_odds_loss = losses['odds'].mean() if not losses.empty else 0
    biggest_win = settled_bets['profit_loss'].max()
    biggest_loss = settled_bets['profit_loss'].min()
    
    # Expected Value calculation
    ev = (wins['profit_loss'].sum() + losses['profit_loss'].sum()) / len(settled_bets) if len(settled_bets) > 0 else 0
    
    # Average stake
    avg_stake = settled_bets['stake'].mean()
    
    # Profit Factor
    total_won = wins['profit_loss'].sum() + wins['stake'].sum() if not wins.empty else 0
    total_lost = losses['stake'].sum() if not losses.empty else 0
    profit_factor = total_won / total_lost if total_lost > 0 else float('inf')
    
    return {
        'avg_win_odds': avg_odds_win,
        'avg_loss_odds': avg_odds_loss,
        'biggest_win': biggest_win,
        'biggest_loss': biggest_loss,
        'expected_value': ev,
        'avg_stake': avg_stake,
        'profit_factor': profit_factor,
        'total_settled_bets': len(settled_bets)
    }

# Bankroll management functions
def get_bankroll():
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    c.execute('SELECT balance FROM bankroll WHERE id = 1')
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def update_bankroll(amount, operation="add"):
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    
    if operation == "add":
        c.execute('UPDATE bankroll SET balance = balance + ? WHERE id = 1', (amount,))
    elif operation == "set":
        c.execute('UPDATE bankroll SET balance = ? WHERE id = 1', (amount,))
    elif operation == "subtract":
        c.execute('UPDATE bankroll SET balance = balance - ? WHERE id = 1', (amount,))
    
    conn.commit()
    conn.close()

# Delete functions
def delete_bet(bet_id):
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    c.execute('DELETE FROM bets WHERE id = ?', (bet_id,))
    conn.commit()
    conn.close()

def delete_quote(quote_id):
    conn = sqlite3.connect('soccer_betting.db')
    c = conn.cursor()
    c.execute('DELETE FROM quotes WHERE id = ?', (quote_id,))
    conn.commit()
    conn.close()

# Export functionality
def export_to_csv():
    df = get_bets()
    csv = df.to_csv(index=False)
    return csv

# Color coding for results
def color_result(val):
    if val == 'Win':
        return 'color: green; font-weight: bold'
    elif val == 'Loss':
        return 'color: red; font-weight: bold'
    elif val == 'Pending':
        return 'color: orange; font-weight: bold'
    else:  # Push
        return 'color: blue; font-weight: bold'

def color_profit_loss(val):
    try:
        num_val = float(val.replace('€', '').replace('+', ''))
        if num_val > 0:
            return 'color: green; font-weight: bold'
        elif num_val < 0:
            return 'color: red; font-weight: bold'
        else:
            return 'color: blue; font-weight: bold'
    except:
        return ''

# Safe display dataframe creation
def create_display_df(bets_df):
    # Define base columns that should always exist
    base_columns = ['id', 'date', 'stake', 'odds', 'result', 'profit_loss', 'notes', 'is_parlay']
    
    # Define new columns that might not exist in old data
    new_columns = ['team_a', 'team_b', 'bet_type', 'sport']
    
    # Start with base columns
    display_columns = base_columns.copy()
    
    # Add new columns only if they exist in the dataframe
    for col in new_columns:
        if col in bets_df.columns:
            display_columns.append(col)
    
    # Create the display dataframe
    display_df = bets_df[display_columns].copy()
    
    # Format columns with euros
    display_df['profit_loss_display'] = display_df['profit_loss'].apply(lambda x: f"€{x:+.2f}")
    display_df['odds'] = display_df['odds'].apply(lambda x: f"{x:.2f}")
    display_df['stake'] = display_df['stake'].apply(lambda x: f"€{x:.2f}")
    
    # Add parlay indicator
    display_df['type'] = display_df['is_parlay'].apply(lambda x: "Parlay 🔥" if x == 1 else "Single")
    
    return display_df, display_columns

# Main app
def main():
    st.set_page_config(
        page_title="Soccer Betting Tracker Pro",
        page_icon="⚽",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Initialize session state
    if 'bets_updated' not in st.session_state:
        st.session_state.bets_updated = False
    if 'quotes_updated' not in st.session_state:
        st.session_state.quotes_updated = False
    if 'delete_confirm' not in st.session_state:
        st.session_state.delete_confirm = False
    if 'parlay_legs' not in st.session_state:
        st.session_state.parlay_legs = []
    if 'editing_bet_id' not in st.session_state:
        st.session_state.editing_bet_id = None
    
    # Initialize database (this will handle migration)
    init_db()
    
    st.title("⚽ Advanced Soccer Betting Dashboard")
    
    # Use tabs for better organization
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 Add New Bet", "📊 Dashboard", "💰 Bankroll Management", "💬 Motivational Quotes"])
    
    with tab1:
        st.header("Add New Bet")
        
        # Bet type selection
        bet_type_choice = st.radio("Bet Type", ["Single Bet", "Parlay Bet"], horizontal=True)
        
        if bet_type_choice == "Single Bet":
            with st.form("single_bet_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                with col1:
                    date = st.date_input("Date", datetime.now())
                    team_a = st.text_input("Team A", placeholder="Home Team")
                    team_b = st.text_input("Team B", placeholder="Away Team")
                    bet_type = st.selectbox("Bet Type", ["Moneyline", "Over/Under", "Handicap", "Both Teams to Score", "Correct Score", "Other"])
                    sport = st.selectbox("Sport", ["Soccer", "Basketball", "Tennis", "Football", "Baseball", "Hockey", "Other"])
                
                with col2:
                    stake = st.number_input("Stake (€)", min_value=0.0, step=10.0, value=100.0)
                    odds = st.number_input("Odds", min_value=1.0, step=0.1, value=2.0, format="%.2f")
                    result = st.selectbox("Result", ["Pending", "Win", "Loss", "Push"])
                    notes = st.text_area("Notes", placeholder="Optional: Add any notes about the bet")
                
                submitted = st.form_submit_button("💾 Add Single Bet", type="primary", use_container_width=True)
                if submitted:
                    try:
                        add_bet(date.strftime("%Y-%m-%d"), team_a, team_b, bet_type, sport, stake, odds, result, notes, is_parlay=False)
                        st.success("✅ Single bet added successfully!")
                        st.session_state.bets_updated = True
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ Error: {e}")
        
        else:  # Parlay Bet
            st.subheader("🔥 Add Parlay Bet")
            
            # Parlay legs management
            st.write("### Parlay Legs")
            
            # Display current legs
            if st.session_state.parlay_legs:
                st.write("**Current Parlay Legs:**")
                for i, leg in enumerate(st.session_state.parlay_legs):
                    col1, col2, col3, col4 = st.columns([3, 3, 2, 1])
                    with col1:
                        st.write(f"**{leg['team_a']}** vs **{leg['team_b']}**")
                    with col2:
                        st.write(f"{leg['bet_type']} - {leg['sport']}")
                    with col3:
                        st.write(f"Odds: {leg['odds']:.2f}")
                    with col4:
                        if st.button("❌", key=f"remove_{i}"):
                            st.session_state.parlay_legs.pop(i)
                            st.rerun()
            
            # Add new leg form
            with st.form("parlay_leg_form"):
                st.write("### Add New Leg to Parlay")
                col1, col2 = st.columns(2)
                
                with col1:
                    leg_team_a = st.text_input("Team A", placeholder="Home Team", key="leg_team_a")
                    leg_team_b = st.text_input("Team B", placeholder="Away Team", key="leg_team_b")
                    leg_bet_type = st.selectbox("Bet Type", ["Moneyline", "Over/Under", "Handicap", "Both Teams to Score", "Correct Score", "Other"], key="leg_bet_type")
                    leg_sport = st.selectbox("Sport", ["Soccer", "Basketball", "Tennis", "Football", "Baseball", "Hockey", "Other"], key="leg_sport")
                
                with col2:
                    leg_odds = st.number_input("Odds", min_value=1.0, step=0.1, value=2.0, format="%.2f", key="leg_odds")
                    leg_notes = st.text_area("Notes", placeholder="Optional notes for this leg", key="leg_notes")
                
                if st.form_submit_button("➕ Add Leg to Parlay", use_container_width=True):
                    if leg_team_a and leg_team_b:
                        new_leg = {
                            'team_a': leg_team_a,
                            'team_b': leg_team_b,
                            'bet_type': leg_bet_type,
                            'sport': leg_sport,
                            'odds': leg_odds,
                            'notes': leg_notes
                        }
                        st.session_state.parlay_legs.append(new_leg)
                        st.success("✅ Leg added to parlay!")
                        st.rerun()
                    else:
                        st.error("Please fill in both teams")
            
            # Parlay summary and submission
            if st.session_state.parlay_legs:
                st.write("---")
                st.subheader("Parlay Summary")
                
                # Calculate combined odds
                combined_odds = calculate_parlay_odds(st.session_state.parlay_legs)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Number of Legs", len(st.session_state.parlay_legs))
                with col2:
                    st.metric("Combined Odds", f"{combined_odds:.2f}")
                with col3:
                    potential_payout = st.number_input("Stake (€)", min_value=0.0, step=10.0, value=100.0, key="parlay_stake")
                    st.metric("Potential Payout", f"€{potential_payout * combined_odds:.2f}")
                
                # Parlay submission form
                with st.form("parlay_bet_form"):
                    parlay_date = st.date_input("Date", datetime.now(), key="parlay_date")
                    parlay_result = st.selectbox("Result", ["Pending", "Win", "Loss", "Push"], key="parlay_result")
                    parlay_notes = st.text_area("Parlay Notes", placeholder="Overall notes for the parlay", key="parlay_notes")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Save Parlay Bet", type="primary", use_container_width=True):
                            try:
                                add_bet(
                                    parlay_date.strftime("%Y-%m-%d"), 
                                    "Parlay", 
                                    f"{len(st.session_state.parlay_legs)} legs", 
                                    "Parlay", 
                                    "Mixed", 
                                    potential_payout, 
                                    combined_odds, 
                                    parlay_result, 
                                    parlay_notes, 
                                    is_parlay=True,
                                    parlay_legs=st.session_state.parlay_legs
                                )
                                st.success("✅ Parlay bet added successfully!")
                                st.session_state.parlay_legs = []  # Clear legs after submission
                                st.session_state.bets_updated = True
                                st.rerun()
                            except ValueError as e:
                                st.error(f"❌ Error: {e}")
                    
                    with col2:
                        if st.form_submit_button("🗑️ Clear Parlay", use_container_width=True, type="secondary"):
                            st.session_state.parlay_legs = []
                            st.rerun()
            else:
                st.info("🎯 Add legs to your parlay using the form above!")
    
    with tab2:
        # Dashboard content
        bets_df = get_bets()
        
        if not bets_df.empty:
            # Basic Metrics
            total_pl, roi, win_rate, total_bets = calculate_metrics(bets_df)
            advanced_metrics = calculate_advanced_metrics(bets_df)
            bankroll = get_bankroll()
            
            # Main Metrics Row
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Total P/L", f"€{total_pl:+.2f}", 
                         delta=f"{total_pl:+.2f}" if total_pl != 0 else None)
            with col2:
                st.metric("ROI", f"{roi:.1f}%")
            with col3:
                st.metric("Win Rate", f"{win_rate:.1f}%")
            with col4:
                st.metric("Total Bets", total_bets)
            with col5:
                st.metric("Bankroll", f"€{bankroll:.2f}")
            
            # Advanced Metrics Row
            if advanced_metrics:
                st.subheader("📈 Advanced Analytics")
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("Avg Win Odds", f"{advanced_metrics['avg_win_odds']:.2f}")
                with col2:
                    st.metric("Expected Value", f"€{advanced_metrics['expected_value']:.2f}")
                with col3:
                    st.metric("Profit Factor", f"{advanced_metrics['profit_factor']:.2f}" if advanced_metrics['profit_factor'] != float('inf') else "∞")
                with col4:
                    st.metric("Biggest Win", f"€{advanced_metrics['biggest_win']:.2f}")
                with col5:
                    st.metric("Biggest Loss", f"€{advanced_metrics['biggest_loss']:.2f}")
            
            # Charts Section
            st.subheader("📊 Performance Charts")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Bankroll Growth Chart
                bets_df['date'] = pd.to_datetime(bets_df['date'])
                chart_df = bets_df.sort_values('date')
                chart_df['cumulative_pl'] = chart_df['profit_loss'].cumsum()
                chart_df['bankroll'] = bankroll + chart_df['cumulative_pl'] - chart_df['cumulative_pl'].iloc[-1] if len(chart_df) > 0 else bankroll
                
                fig1 = px.line(chart_df, x='date', y='cumulative_pl',
                            title='Profit/Loss Over Time',
                            labels={'date': 'Date', 'cumulative_pl': 'Profit/Loss (€)'})
                fig1.update_traces(line=dict(color='#00FF00', width=3))
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                # Results Distribution
                results_count = bets_df['result'].value_counts()
                fig2 = px.pie(values=results_count.values, names=results_count.index,
                            title='Bet Results Distribution',
                            color=results_count.index,
                            color_discrete_map={'Win':'green', 'Loss':'red', 'Pending':'orange', 'Push':'blue'})
                st.plotly_chart(fig2, use_container_width=True)
            
            # Sport Performance (only if sport column exists and has data)
            if 'sport' in bets_df.columns and not bets_df['sport'].isna().all():
                st.subheader("🏆 Performance by Sport")
                sport_stats = bets_df.groupby('sport').agg({
                    'profit_loss': 'sum',
                    'stake': 'sum',
                    'result': lambda x: (x == 'Win').sum() / len(x) * 100
                }).round(2)
                sport_stats.columns = ['Total P/L', 'Total Stake', 'Win Rate %']
                st.dataframe(sport_stats, use_container_width=True)
            
            # Recent bets with safe display
            st.subheader("📋 Bet History")
            display_df, display_columns = create_display_df(bets_df)
            
            # Create final display columns in the right order
            final_display_columns = ['id', 'date', 'type']
            if 'team_a' in display_columns:
                final_display_columns.extend(['team_a', 'team_b'])
            if 'bet_type' in display_columns:
                final_display_columns.append('bet_type')
            if 'sport' in display_columns:
                final_display_columns.append('sport')
            final_display_columns.extend(['stake', 'odds', 'result', 'profit_loss_display', 'notes'])
            
            # Apply styling
            styled_df = display_df[final_display_columns].style.applymap(
                color_result, subset=['result']).applymap(color_profit_loss, subset=['profit_loss_display'])
            
            st.dataframe(styled_df, use_container_width=True)
            
            # Edit Bet Section
            st.subheader("✏️ Edit Bet")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Select bet to edit
                edit_options = []
                for _, row in bets_df.iterrows():
                    option_text = f"ID {row['id']}: "
                    if row.get('is_parlay') == 1:
                        option_text += f"PARLAY - {row.get('team_a', 'Parlay')} - "
                    elif 'team_a' in bets_df.columns and row['team_a'] and row['team_b']:
                        option_text += f"{row['team_a']} vs {row['team_b']} - "
                    option_text += f"€{row['stake']} at {row['odds']}x ({row['result']})"
                    edit_options.append(option_text)
                
                bet_to_edit = st.selectbox("Select bet to edit:", edit_options, key="edit_select")
                bet_id_to_edit = int(bet_to_edit.split(":")[0].replace("ID ", ""))
                
                if st.button("✏️ Edit Selected Bet", use_container_width=True):
                    st.session_state.editing_bet_id = bet_id_to_edit
                    st.rerun()
            
            with col2:
                if st.session_state.editing_bet_id:
                    st.info(f"Editing Bet ID: {st.session_state.editing_bet_id}")
                    if st.button("❌ Cancel Edit", use_container_width=True):
                        st.session_state.editing_bet_id = None
                        st.rerun()
            
            # Edit Bet Form
            if st.session_state.editing_bet_id:
                bet_to_edit = get_bet_by_id(st.session_state.editing_bet_id)
                if bet_to_edit:
                    st.write("---")
                    st.subheader(f"Editing Bet ID: {st.session_state.editing_bet_id}")
                    
                    with st.form("edit_bet_form"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            edit_date = st.date_input("Date", datetime.strptime(bet_to_edit['date'], "%Y-%m-%d"))
                            edit_team_a = st.text_input("Team A", value=bet_to_edit['team_a'])
                            edit_team_b = st.text_input("Team B", value=bet_to_edit['team_b'])
                            edit_bet_type = st.selectbox("Bet Type", 
                                                       ["Moneyline", "Over/Under", "Handicap", "Both Teams to Score", "Correct Score", "Other", "Parlay"],
                                                       index=["Moneyline", "Over/Under", "Handicap", "Both Teams to Score", "Correct Score", "Other", "Parlay"].index(bet_to_edit['bet_type']) if bet_to_edit['bet_type'] in ["Moneyline", "Over/Under", "Handicap", "Both Teams to Score", "Correct Score", "Other", "Parlay"] else 0)
                            edit_sport = st.selectbox("Sport", 
                                                    ["Soccer", "Basketball", "Tennis", "Football", "Baseball", "Hockey", "Other", "Mixed"],
                                                    index=["Soccer", "Basketball", "Tennis", "Football", "Baseball", "Hockey", "Other", "Mixed"].index(bet_to_edit['sport']) if bet_to_edit['sport'] in ["Soccer", "Basketball", "Tennis", "Football", "Baseball", "Hockey", "Other", "Mixed"] else 0)
                        
                        with col2:
                            edit_stake = st.number_input("Stake (€)", min_value=0.0, step=10.0, value=float(bet_to_edit['stake']))
                            edit_odds = st.number_input("Odds", min_value=1.0, step=0.1, value=float(bet_to_edit['odds']), format="%.2f")
                            edit_result = st.selectbox("Result", ["Pending", "Win", "Loss", "Push"], 
                                                     index=["Pending", "Win", "Loss", "Push"].index(bet_to_edit['result']))
                            edit_notes = st.text_area("Notes", value=bet_to_edit['notes'])
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Update Bet", type="primary", use_container_width=True):
                                try:
                                    update_bet(
                                        st.session_state.editing_bet_id,
                                        edit_date.strftime("%Y-%m-%d"),
                                        edit_team_a,
                                        edit_team_b,
                                        edit_bet_type,
                                        edit_sport,
                                        edit_stake,
                                        edit_odds,
                                        edit_result,
                                        edit_notes,
                                        is_parlay=bool(bet_to_edit['is_parlay'])
                                    )
                                    st.success("✅ Bet updated successfully!")
                                    st.session_state.editing_bet_id = None
                                    st.session_state.bets_updated = True
                                    st.rerun()
                                except ValueError as e:
                                    st.error(f"❌ Error: {e}")
                        
                        with col2:
                            if st.form_submit_button("❌ Cancel", use_container_width=True, type="secondary"):
                                st.session_state.editing_bet_id = None
                                st.rerun()
            
            # Export functionality
            st.subheader("📥 Export Data")
            csv_data = export_to_csv()
            st.download_button(
                label="📥 Export All Bets to CSV",
                data=csv_data,
                file_name=f"betting_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            # Enhanced delete option with confirmation
            st.subheader("🗑️ Manage Bets")
            if not bets_df.empty:
                # Create delete options
                delete_options = []
                for _, row in bets_df.iterrows():
                    option_text = f"ID {row['id']}: "
                    if row.get('is_parlay') == 1:
                        option_text += f"PARLAY - {row.get('team_a', 'Parlay')} - "
                    elif 'team_a' in bets_df.columns and row['team_a'] and row['team_b']:
                        option_text += f"{row['team_a']} vs {row['team_b']} - "
                    option_text += f"€{row['stake']} at {row['odds']}x ({row['date']})"
                    delete_options.append(option_text)
                
                bet_to_delete = st.selectbox("Select bet to delete:", delete_options, key="delete_select")
                
                col1, col2 = st.columns([1, 4])
                with col1:
                    if st.button("🗑️ Delete Bet", use_container_width=True, type="secondary"):
                        st.session_state.delete_confirm = True
                
                if st.session_state.delete_confirm:
                    with col2:
                        st.warning("⚠️ Confirm Deletion")
                        if st.button("✅ Confirm Delete", key="confirm_delete", use_container_width=True):
                            bet_id = int(bet_to_delete.split(":")[0].replace("ID ", ""))
                            delete_bet(bet_id)
                            st.success("✅ Bet deleted successfully!")
                            st.session_state.delete_confirm = False
                            st.session_state.bets_updated = True
                            st.rerun()
                        if st.button("❌ Cancel", key="cancel_delete", use_container_width=True):
                            st.session_state.delete_confirm = False
                            st.rerun()
            
        else:
            st.info("🎯 No bets recorded yet. Add your first bet in the 'Add New Bet' tab!")
    
    with tab3:
        st.header("💰 Bankroll Management")
        
        current_bankroll = get_bankroll()
        st.metric("Current Bankroll", f"€{current_bankroll:.2f}")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("Add Funds")
            with st.form("add_funds"):
                add_amount = st.number_input("Amount to Add (€)", min_value=1.0, step=1.0, value=10.0, key="add_amount")
                if st.form_submit_button("💵 Add Funds", use_container_width=True):
                    update_bankroll(add_amount, "add")
                    st.success(f"✅ Added €{add_amount:.2f} to bankroll!")
                    st.rerun()
        
        with col2:
            st.subheader("Withdraw Funds")
            with st.form("withdraw_funds"):
                withdraw_amount = st.number_input("Amount to Withdraw (€)", min_value=1.0, step=1.0, value=10.0, key="withdraw_amount", max_value=current_bankroll)
                if st.form_submit_button("💸 Withdraw Funds", use_container_width=True):
                    update_bankroll(withdraw_amount, "subtract")
                    st.success(f"✅ Withdrew €{withdraw_amount:.2f} from bankroll!")
                    st.rerun()
        
        with col3:
            st.subheader("Set Bankroll")
            with st.form("set_bankroll"):
                new_bankroll = st.number_input("New Bankroll Amount (€)", min_value=0.0, step=1.0, value=current_bankroll, key="set_amount")
                if st.form_submit_button("⚙️ Set Bankroll", use_container_width=True):
                    update_bankroll(new_bankroll, "set")
                    st.success(f"✅ Bankroll set to €{new_bankroll:.2f}!")
                    st.rerun()
        
        # Bankroll statistics
        st.subheader("📈 Bankroll Statistics")
        if not bets_df.empty:
            total_stake = bets_df['stake'].sum()
            suggested_stake = current_bankroll * 0.02  # 2% of bankroll
            risk_per_bet = (bets_df['stake'] / current_bankroll).mean() * 100 if current_bankroll > 0 else 0
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Amount Wagered", f"€{total_stake:.2f}")
            with col2:
                st.metric("Suggested Stake (2%)", f"€{suggested_stake:.2f}")
            with col3:
                st.metric("Avg Risk per Bet", f"{risk_per_bet:.1f}%")
    
    with tab4:
        st.header("💭 Motivational Quotes")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            quotes_df = get_quotes()
            if not quotes_df.empty:
                for _, quote in quotes_df.iterrows():
                    with st.container():
                        st.info(f"**{quote['category']}:**\n\n\"{quote['quote_text']}\"")
                        col_a, col_b = st.columns([1, 6])
                        with col_a:
                            if st.button(f"Delete", key=f"del_quote_{quote['id']}"):
                                delete_quote(quote['id'])
                                st.session_state.quotes_updated = True
                                st.rerun()
            else:
                st.write("No quotes yet. Add one below!")
        
        with col2:
            st.subheader("Add New Quote")
            with st.form("quote_form", clear_on_submit=True):
                quote = st.text_area("Enter your motivational quote", height=100)
                category = st.selectbox("Category", ["Motivation", "Discipline", "Strategy", "Mindset", "Inspiration", "Other"])
                if st.form_submit_button("💾 Save Quote", use_container_width=True):
                    if quote:
                        add_quote(quote, category)
                        st.success("✅ Quote saved!")
                        st.session_state.quotes_updated = True
                        st.rerun()

if __name__ == "__main__":
    main()